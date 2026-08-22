"""Sales commissions — forecast on the open book, earned on the won one.

A rep's commission is a percentage of a deal's value, and the deal is theirs
because they EARNED it: ``crm_deals.commission_rep_user_id`` (migration 264),
set once by the first real sales action and never moved by a later
reassignment. ``owner_user_id`` — who is working the club right now — is
deliberately NOT what any figure here is keyed on, or a rep's quarter would
change the moment a super admin handed one of their clubs to someone else.

**A deal's dollar figure has one definition and this file does not own it.**
``crm.effective_value_cents`` (module-derived price, minus any discretionary
discount) and ``crm.effective_probability`` (the deal's own likelihood, else
its stage's) are what the Sales Pipeline board's own totals are built from,
so a rep's forecast and the board can never disagree about the same deal.

**The rate is live for a forecast and stamped for a win.** An open deal is
forecast at the rep's CURRENT rate, because a forecast is about what is still
to come. The moment a deal is won, the rate that applied is written onto it
(``crm_deals.commission_rate_percent``), so raising a rep's rate tomorrow
cannot rewrite what they earned last quarter. A deal won before that column
existed carries NULL and falls back to the rep's current rate — the only
answer available for it, and the same one it would have had all along at an
unchanged rate.

**A rep is a PERSON, not an account.** One person can hold several login
accounts, and one account several membership rows; ``crm.list_platform_owners``
already folds those into one entry, and every figure here is aggregated over
that entry's whole set of account ids. A rate or a payment is WRITTEN against
the entry's primary id but READ across all of them, because which account
counts as primary can shift (it is partly last-login order) and a payout must
not go missing when it does.
"""
from __future__ import annotations

import logging
import uuid as _uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CrmDeal, MarketingClub, SalesCommissionPayment, SalesCommissionRate, User,
)
from app.services import crm as crm_service
from app.services import crm_targets

logger = logging.getLogger(__name__)

# The unattributed row: won and open deals nobody has earned. It is shown
# rather than dropped — a pipeline nobody is going to be paid for is exactly
# the thing a commission screen should make visible.
UNATTRIBUTED_KEY = "unattributed"

# How far back the period summary looks. Fixed counts rather than "whatever
# the data reaches", so the table is the same shape week to week and a quarter
# with nothing in it still reads as a quarter with nothing in it.
QUARTERS_SHOWN = 8
FISCAL_YEARS_SHOWN = 3

MAX_RATE_PERCENT = Decimal("100")


def _q(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def commission_cents(value_cents: int, rate_percent: Decimal) -> int:
    """Commission on a dollar figure, in whole cents. Rounded half-up once,
    at the end — never a sum of separately-rounded per-deal figures, or a
    rep's total drifts from the deals it is made of by a cent per deal."""
    if not value_cents or not rate_percent:
        return 0
    return int((Decimal(value_cents) * Decimal(rate_percent) / Decimal(100))
               .quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# ─── Rates ───────────────────────────────────────────────────────────────────

async def load_rates(session: AsyncSession) -> dict:
    """``{"default": Decimal, "by_account": {account_id_str: Decimal}}``.

    ``by_account`` is keyed on the raw ``users.id`` a row was written against,
    NOT on a folded rep entry — the fold is applied by the caller, which is
    what lets a rate survive the entry's primary account changing."""
    rows = (await session.execute(select(SalesCommissionRate))).scalars().all()
    default = Decimal("0")
    by_account: dict[str, Decimal] = {}
    for r in rows:
        if r.user_id is None:
            default = Decimal(r.rate_percent or 0)
        else:
            by_account[str(r.user_id)] = Decimal(r.rate_percent or 0)
    return {"default": default, "by_account": by_account}


def rate_for(rates: dict, account_ids) -> Decimal:
    """The rate that applies to a rep, given every account id they hold. The
    HIGHEST of the rates actually set on their accounts wins — a person with
    two accounts should never be paid the lower of two rates because of which
    account a deal happened to land on. No account carries a rate of its own,
    so the platform default applies."""
    found = [rates["by_account"][a] for a in account_ids if a in rates["by_account"]]
    return max(found) if found else rates["default"]


async def set_rate(session: AsyncSession, *, user_id, rate_percent, actor_user_id=None) -> Decimal:
    """Write a rep's rate, or the platform default when ``user_id`` is None.
    Caller commits. Raises ValueError on a rate outside 0–100."""
    try:
        rate = _q(Decimal(str(rate_percent)))
    except Exception as exc:  # noqa: BLE001 - any unparseable input is the same refusal
        raise ValueError("Enter a commission rate as a percentage") from exc
    if rate < 0 or rate > MAX_RATE_PERCENT:
        raise ValueError("A commission rate must be between 0 and 100 percent")

    stmt = select(SalesCommissionRate)
    stmt = stmt.where(SalesCommissionRate.user_id == user_id) if user_id is not None \
        else stmt.where(SalesCommissionRate.user_id.is_(None))
    row = (await session.execute(stmt)).scalars().first()
    if row is None:
        row = SalesCommissionRate(user_id=user_id, rate_percent=rate)
        session.add(row)
    else:
        row.rate_percent = rate
    row.updated_by_user_id = actor_user_id
    row.updated_at = datetime.now(timezone.utc)
    await session.flush()
    return rate


async def stamp_won_rate(session: AsyncSession, deal: CrmDeal) -> None:
    """Write the rate that applied onto a deal at the moment it is won.

    Called from the two places a deal's status becomes 'won'
    (``crm.move_stage`` and ``crm.close_deal``), so a win through the board,
    through the Stripe webhook, or through an automation rule is all one
    behaviour. Best-effort by design: a commission bookkeeping hiccup must
    never fail the write that recorded the sale itself. A deal with no rep
    attributed gets the platform default — the only rate knowable for it, and
    it earns nobody anything until a rep is attributed anyway."""
    try:
        rates = await load_rates(session)
        account_ids = [str(deal.commission_rep_user_id)] if deal.commission_rep_user_id else []
        deal.commission_rate_percent = rate_for(rates, account_ids)
    except Exception:  # noqa: BLE001
        logger.exception("commission: could not stamp the won rate on deal %s", deal.id)


# ─── Rep entries ─────────────────────────────────────────────────────────────

async def _rep_entries(session: AsyncSession) -> list[dict]:
    """Every sales rep, folded to one entry per person (see the module note).
    A super admin is never a rep: only a rep can be attributed a club at all
    (see services/sales_workspace.py's commission note), so one appearing here
    would be a row that can only ever read zero."""
    return await crm_service.list_platform_owners(session, roles=("sales",))


def _entry_of_account(entries: list[dict]) -> dict:
    """account_id_str -> the entry it belongs to."""
    return {aid: e for e in entries for aid in (e.get("ids") or [e["id"]])}


async def _attributed_deals(session: AsyncSession) -> list[CrmDeal]:
    """Every non-archived platform deal, attributed or not. The unattributed
    ones are the pool this screen exists to make visible, so they are not
    filtered out here — the caller files them under UNATTRIBUTED_KEY."""
    pipeline = await crm_service.ensure_platform_pipeline(session)
    return (await session.execute(
        select(CrmDeal).where(
            CrmDeal.pipeline_id == pipeline.id,
            CrmDeal.archived_at.is_(None),
        )
    )).scalars().all()


async def _stage_by_id(session: AsyncSession) -> dict:
    pipeline = await crm_service.ensure_platform_pipeline(session)
    return {s.id: s for s in pipeline.stages}


def _blank_row() -> dict:
    return {
        "clubs_attributed": 0,
        "open_deals": 0,
        "pipeline_value_cents": 0,
        "weighted_pipeline_value_cents": 0,
        "forecast_commission_cents": 0,
        "weighted_forecast_commission_cents": 0,
        "won_deals": 0,
        "won_value_cents": 0,
        "commission_earned_cents": 0,
        "commission_paid_cents": 0,
        "commission_due_cents": 0,
    }


# ─── The report ──────────────────────────────────────────────────────────────

async def commission_report(session: AsyncSession, *, rep_user_id=None) -> dict:
    """Forecast and earned commission per rep, plus the totals row.

    ``rep_user_id`` pins the report to one rep (every account that person
    holds), for a caller that must not see the whole team's numbers.

    Per rep:

    * ``clubs_attributed`` — DISTINCT clubs, not deals. A club that came back
      for more modules has a second deal, and counting it twice would read as
      two clubs won.
    * ``pipeline_value_cents`` / ``weighted_pipeline_value_cents`` — their OPEN
      deals at full value, and at value × the deal's own likelihood.
    * the two forecast commission figures — each of those at their live rate.
    * ``won_*`` / ``commission_earned_cents`` — their won deals, each at the
      rate stamped when it was won.

    The Unattributed row is rated at ZERO throughout: its pipeline value is
    worth seeing (it is unclaimed work), but no commission is owed on a club
    nobody has earned.
    * ``commission_paid_cents`` / ``commission_due_cents`` — against the
      payments ledger. Due is earned minus paid and is allowed to go negative
      (an overpayment is a real state and hiding it would lose it).
    """
    entries = await _rep_entries(session)
    by_account = _entry_of_account(entries)
    rates = await load_rates(session)
    stage_by_id = await _stage_by_id(session)
    deals = await _attributed_deals(session)

    pinned_ids = None
    if rep_user_id is not None:
        entry = by_account.get(str(rep_user_id))
        pinned_ids = set(entry["ids"]) if entry else {str(rep_user_id)}
        entries = [e for e in entries if set(e.get("ids") or [e["id"]]) & pinned_ids]

    rows: dict[str, dict] = {}
    clubs_seen: dict[str, set] = {}

    def _bucket(key: str, name: str, rate: Decimal) -> dict:
        if key not in rows:
            rows[key] = {"rep_user_id": key, "rep_name": name,
                        "unattributed": key == UNATTRIBUTED_KEY,
                        "rate_percent": float(rate), **_blank_row()}
            clubs_seen[key] = set()
        return rows[key]

    for e in entries:
        _bucket(e["id"], e["name"], rate_for(rates, e.get("ids") or [e["id"]]))

    for d in deals:
        rep_account = str(d.commission_rep_user_id) if d.commission_rep_user_id else None
        entry = by_account.get(rep_account) if rep_account else None
        if entry is not None:
            key, name, live_rate = entry["id"], entry["name"], rate_for(rates, entry.get("ids") or [entry["id"]])
        elif rep_account is not None:
            # Attributed to an account that is no longer a sales rep (the role
            # was changed, or the person left). The work still happened and the
            # money is still owed, so the rep keeps their row rather than the
            # deal silently reading as unattributed.
            key, name, live_rate = rep_account, "Former rep", rates["default"]
        else:
            if pinned_ids is not None:
                continue
            # The pool is rated at ZERO, deliberately. Its pipeline VALUE is
            # the useful figure — unclaimed work waiting for a rep — but no
            # commission is owed on a club nobody has earned, and pricing it
            # at the default would inflate the team's forecast with money that
            # will never be paid to anyone.
            key, name, live_rate = UNATTRIBUTED_KEY, "Unattributed", Decimal("0")
        if pinned_ids is not None and rep_account not in pinned_ids:
            continue

        row = _bucket(key, name, live_rate)
        clubs_seen[key].add(str(d.marketing_club_id or d.id))

        value = crm_service.effective_value_cents(d)
        if d.status == "open":
            prob = crm_service.effective_probability(d, stage_by_id.get(d.stage_id)) or 0
            row["open_deals"] += 1
            row["pipeline_value_cents"] += value
            row["weighted_pipeline_value_cents"] += round(value * prob / 100)
        elif d.status == "won":
            # The rate stamped at the win, else the rep's current one for a
            # deal won before that column existed.
            won_rate = Decimal(d.commission_rate_percent) if d.commission_rate_percent is not None else live_rate
            row["won_deals"] += 1
            row["won_value_cents"] += value
            row["commission_earned_cents"] += commission_cents(value, won_rate)

    payments = await _payments_by_account(session)
    for key, row in rows.items():
        rate = Decimal(str(row["rate_percent"]))
        row["clubs_attributed"] = len(clubs_seen[key])
        row["forecast_commission_cents"] = commission_cents(row["pipeline_value_cents"], rate)
        row["weighted_forecast_commission_cents"] = commission_cents(
            row["weighted_pipeline_value_cents"], rate)
        entry = next((e for e in entries if e["id"] == key), None)
        account_ids = (entry.get("ids") or [entry["id"]]) if entry else [key]
        row["commission_paid_cents"] = sum(payments.get(a, 0) for a in account_ids)
        row["commission_due_cents"] = row["commission_earned_cents"] - row["commission_paid_cents"]

    out = list(rows.values())
    # Unattributed always last: it is the pool, not a person's performance —
    # the same rule the Sales Performance table's own Unassigned row follows.
    out.sort(key=lambda r: (r["unattributed"], -r["commission_due_cents"],
                            -r["pipeline_value_cents"], (r["rep_name"] or "").lower()))

    totals = _blank_row()
    for r in out:
        for k in totals:
            totals[k] += r[k]

    return {
        "rows": out,
        "totals": totals,
        "default_rate_percent": float(rates["default"]),
        "rate_set": bool(rates["default"] or rates["by_account"]),
    }


async def _payments_by_account(session: AsyncSession, *, start: Optional[date] = None,
                               end: Optional[date] = None) -> dict:
    stmt = select(SalesCommissionPayment)
    if start is not None:
        stmt = stmt.where(SalesCommissionPayment.paid_on >= start)
    if end is not None:
        stmt = stmt.where(SalesCommissionPayment.paid_on < end)
    rows = (await session.execute(stmt)).scalars().all()
    out: dict[str, int] = {}
    for p in rows:
        key = str(p.rep_user_id)
        out[key] = out.get(key, 0) + int(p.amount_cents or 0)
    return out


# ─── Periods ─────────────────────────────────────────────────────────────────

def period_keys(period_type: str, now: Optional[datetime] = None) -> list[str]:
    """The keys the summary covers, oldest first and ending with the one
    running now. Quarters are calendar quarters and a fiscal year runs 1 Jul
    to 30 Jun named for the year it ENDS in — both straight from
    ``crm_targets.period_bounds``, so a commission period and a sales target
    period mean the same thing rather than being two conventions."""
    now = now or datetime.now(timezone.utc)
    if period_type == "quarter":
        year, q = now.year, (now.month - 1) // 3 + 1
        keys = []
        for _ in range(QUARTERS_SHOWN):
            keys.append(f"{year}-Q{q}")
            q -= 1
            if q == 0:
                q, year = 4, year - 1
        return list(reversed(keys))
    if period_type == "fiscal_year":
        fy = now.year + 1 if now.month >= 7 else now.year
        return [f"FY{fy - i}" for i in range(FISCAL_YEARS_SHOWN - 1, -1, -1)]
    raise ValueError(f"Unknown period_type: {period_type!r}")


def period_label(period_type: str, key: str) -> str:
    if period_type == "fiscal_year":
        year = int(key[2:])
        return f"FY{year} ({year - 1}/{str(year)[2:]})"
    year, q = key.split("-Q")
    months = {"1": "Jan–Mar", "2": "Apr–Jun", "3": "Jul–Sep", "4": "Oct–Dec"}[q]
    return f"{key} ({months} {year})"


async def period_summary(session: AsyncSession, *, period_type: str = "quarter",
                         rep_user_id=None) -> dict:
    """Commission earned and paid, per period and per rep.

    Earned is filed by the deal's ``closed_at`` — when it was actually won —
    and paid by the payment's own ``paid_on``. The two therefore legitimately
    land in different periods: a quarter's work is routinely paid in the next
    one, and forcing a payment into the period it settled would be inventing
    an apportionment nobody made."""
    keys = period_keys(period_type)
    entries = await _rep_entries(session)
    by_account = _entry_of_account(entries)
    rates = await load_rates(session)
    deals = await _attributed_deals(session)
    won = [d for d in deals if d.status == "won" and d.closed_at is not None]

    pinned_ids = None
    if rep_user_id is not None:
        entry = by_account.get(str(rep_user_id))
        pinned_ids = set(entry["ids"]) if entry else {str(rep_user_id)}

    payments = (await session.execute(select(SalesCommissionPayment))).scalars().all()

    periods = []
    for key in keys:
        start, end = crm_targets.period_bounds(period_type, key)
        rows: dict[str, dict] = {}

        def _row(rkey: str, name: str) -> dict:
            return rows.setdefault(rkey, {"rep_user_id": rkey, "rep_name": name,
                                         "earned_cents": 0, "paid_cents": 0})

        for d in won:
            closed = d.closed_at
            if closed.tzinfo is None:
                closed = closed.replace(tzinfo=timezone.utc)
            if not (start <= closed < end):
                continue
            account = str(d.commission_rep_user_id) if d.commission_rep_user_id else None
            if pinned_ids is not None and account not in pinned_ids:
                continue
            entry = by_account.get(account) if account else None
            if entry is not None:
                rkey, name = entry["id"], entry["name"]
                live = rate_for(rates, entry.get("ids") or [entry["id"]])
            elif account is not None:
                rkey, name, live = account, "Former rep", rates["default"]
            else:
                if pinned_ids is not None:
                    continue
                # Zero, for the reason commission_report gives: nobody has
                # earned the pool, so nobody is owed anything on it.
                rkey, name, live = UNATTRIBUTED_KEY, "Unattributed", Decimal("0")
            rate = Decimal(d.commission_rate_percent) if d.commission_rate_percent is not None else live
            _row(rkey, name)["earned_cents"] += commission_cents(
                crm_service.effective_value_cents(d), rate)

        for p in payments:
            if not (start.date() <= p.paid_on < end.date()):
                continue
            account = str(p.rep_user_id)
            if pinned_ids is not None and account not in pinned_ids:
                continue
            entry = by_account.get(account)
            rkey = entry["id"] if entry else account
            name = entry["name"] if entry else "Former rep"
            _row(rkey, name)["paid_cents"] += int(p.amount_cents or 0)

        rows_out = sorted(rows.values(), key=lambda r: (r["rep_user_id"] == UNATTRIBUTED_KEY,
                                                       (r["rep_name"] or "").lower()))
        periods.append({
            "key": key,
            "label": period_label(period_type, key),
            "rows": rows_out,
            "totals": {
                "earned_cents": sum(r["earned_cents"] for r in rows_out),
                "paid_cents": sum(r["paid_cents"] for r in rows_out),
            },
        })
    return {"period_type": period_type, "periods": periods}


# ─── Payments ────────────────────────────────────────────────────────────────

async def record_payment(session: AsyncSession, *, rep_user_id, amount_cents: int,
                         paid_on: date, reference: Optional[str] = None,
                         note: Optional[str] = None,
                         actor_user_id=None) -> SalesCommissionPayment:
    """Record one payout. Caller commits.

    A NEGATIVE amount is deliberately allowed: it is how a payment entered
    wrongly is corrected without deleting the original, which is what an
    auditable ledger needs. A zero is refused — it records nothing."""
    if not amount_cents:
        raise ValueError("Enter an amount")
    payment = SalesCommissionPayment(
        rep_user_id=rep_user_id, amount_cents=int(amount_cents), paid_on=paid_on,
        reference=(reference or "").strip()[:200] or None,
        note=(note or "").strip()[:1000] or None,
        created_by_user_id=actor_user_id,
    )
    session.add(payment)
    await session.flush()
    return payment


async def delete_payment(session: AsyncSession, payment_id) -> bool:
    result = await session.execute(
        delete(SalesCommissionPayment).where(SalesCommissionPayment.id == payment_id))
    return bool(result.rowcount)


async def list_payments(session: AsyncSession, *, rep_user_id=None, limit: int = 200) -> list[dict]:
    stmt = select(SalesCommissionPayment).order_by(
        SalesCommissionPayment.paid_on.desc(), SalesCommissionPayment.created_at.desc()
    ).limit(max(1, min(int(limit or 200), 500)))
    if rep_user_id is not None:
        entries = await _rep_entries(session)
        entry = _entry_of_account(entries).get(str(rep_user_id))
        ids = [_uuid.UUID(a) for a in (entry["ids"] if entry else [str(rep_user_id)])]
        stmt = stmt.where(SalesCommissionPayment.rep_user_id.in_(ids))
    rows = (await session.execute(stmt)).scalars().all()
    names = await _names_by_ids(session, {p.rep_user_id for p in rows}
                                | {p.created_by_user_id for p in rows if p.created_by_user_id})
    return [{
        "id": str(p.id),
        "rep_user_id": str(p.rep_user_id),
        "rep_name": names.get(p.rep_user_id) or "Unknown",
        "amount_cents": int(p.amount_cents or 0),
        "paid_on": p.paid_on.isoformat() if p.paid_on else None,
        "reference": p.reference,
        "note": p.note,
        "recorded_by": names.get(p.created_by_user_id),
        "created_at": p.created_at.isoformat() if p.created_at else None,
    } for p in rows]


async def _names_by_ids(session: AsyncSession, ids) -> dict:
    ids = {i for i in ids if i}
    if not ids:
        return {}
    rows = (await session.execute(select(User).where(User.id.in_(ids)))).scalars().all()
    return {u.id: (u.display_name or u.username) for u in rows}


# ─── Drill-down: the deals behind a rep's figures ────────────────────────────

async def rep_deals(session: AsyncSession, *, rep_user_id: str, status: str = "open",
                    pinned_rep_id=None) -> dict:
    """The deals behind one rep's forecast or won figure.

    Re-runs the very predicates ``commission_report`` used rather than a query
    shaped like them, so a row reading five deals can never open four — the
    rule the Sales Performance drill-downs already follow.
    """
    if status not in ("open", "won"):
        raise ValueError(f"unknown status {status!r}")
    entries = await _rep_entries(session)
    by_account = _entry_of_account(entries)
    rates = await load_rates(session)
    stage_by_id = await _stage_by_id(session)

    if pinned_rep_id is not None:
        rep_user_id = str(pinned_rep_id)
    entry = by_account.get(str(rep_user_id))
    if rep_user_id == UNATTRIBUTED_KEY:
        wanted, live = None, Decimal("0")
    else:
        wanted = set(entry["ids"]) if entry else {str(rep_user_id)}
        live = rate_for(rates, sorted(wanted))

    def _account_of(deal: CrmDeal) -> Optional[str]:
        return str(deal.commission_rep_user_id) if deal.commission_rep_user_id else None

    def _mine(deal: CrmDeal) -> bool:
        account = _account_of(deal)
        return account is None if wanted is None else account in wanted

    deals = [d for d in await _attributed_deals(session)
             if d.status == status and _mine(d)]

    club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))
    out = []
    for d in deals:
        club: Optional[MarketingClub] = club_by_id.get(d.marketing_club_id)
        value = crm_service.effective_value_cents(d)
        stage = stage_by_id.get(d.stage_id)
        prob = crm_service.effective_probability(d, stage) or 0
        rate = (Decimal(d.commission_rate_percent) if (status == "won" and d.commission_rate_percent is not None)
                else live)
        out.append({
            "deal_id": str(d.id),
            "club_name": (club.name if club else None) or d.title or "Untitled",
            "state": club.state if club else None,
            "stage_name": stage.name if stage else None,
            "probability": prob,
            "module_keys": sorted(d.module_keys or []),
            "value_cents": value,
            "weighted_value_cents": round(value * prob / 100),
            "rate_percent": float(rate),
            "commission_cents": commission_cents(value, rate),
            "weighted_commission_cents": commission_cents(round(value * prob / 100), rate),
            "closed_at": d.closed_at.isoformat() if d.closed_at else None,
        })
    out.sort(key=lambda r: (-r["value_cents"], r["club_name"].lower()))
    return {"deals": out, "count": len(out)}
