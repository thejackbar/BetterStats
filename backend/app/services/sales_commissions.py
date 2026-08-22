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
    BillingInvoice, CrmDeal, MarketingClub, Organisation, SalesCommissionPayment,
    SalesCommissionRate, User,
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


# ``crm_deals.commission_rate_percent`` (migration 277) is left in place and
# NOTHING reads it since 278 — the same call migration 267 made for
# ``vote_settings``. It was the deal-based model's stamp; commission is now
# earned on a payment and stamped on the invoice, so a second rate living on
# the deal could only ever drift from the one that was actually paid.


# ─── Earned: a confirmed Stripe payment ──────────────────────────────────────
#
# EARNED COMMISSION COMES FROM MONEY ARRIVING, NOT FROM A DEAL'S STAGE (per
# direct instruction). A stage is a human judgement someone can drag around;
# a paid Stripe invoice is a fact, and it is the only thing here that creates
# an entitlement to be paid.
#
# Only NEW BUSINESS earns, and Stripe's own ``billing_reason`` is what says
# which — no inference from line items:
#
#   subscription_create  the club's first paid invoice          -> 'initial'
#   subscription_update  modules added to a live subscription   -> 'expansion'
#   subscription_cycle   a renewal of what they already hold    -> earns nothing
#
# A renewal is the club not cancelling, which is not a sale. Commission is
# calculated NET OF GST: tax collected on our behalf was never our revenue.

COMMISSIONABLE_BILLING_REASONS = {
    "subscription_create": "initial",
    "subscription_update": "expansion",
}


def invoice_ex_tax_cents(invoice: dict) -> int:
    """What the club actually paid, net of tax, from a Stripe invoice payload.

    ``total_excluding_tax`` is Stripe's own answer and is preferred. Older API
    versions omit it, so the fallback subtracts the invoice's own tax amounts
    from what was paid; a payload with neither falls back to ``amount_paid``,
    which over-credits by the GST rather than crediting nothing."""
    ex = invoice.get("total_excluding_tax")
    if ex is not None:
        return int(ex)
    paid = int(invoice.get("amount_paid") or 0)
    tax = invoice.get("tax")
    if tax is None:
        tax = sum(int(t.get("amount") or 0) for t in (invoice.get("total_tax_amounts") or []))
    return max(0, paid - int(tax or 0))


async def _club_and_rep_for_org(session: AsyncSession, org_id):
    """(MarketingClub, rep_user_id) for a paying club — the rep who EARNED it.

    The club's directory row is what links a paying Organisation back to the
    pipeline, and the rep is whoever the club's most recently attributed deal
    names. An unlinked or never-attributed club resolves to no rep, and its
    payments then earn nobody anything rather than being quietly dropped."""
    club = (await session.execute(
        select(MarketingClub).where(MarketingClub.existing_org_id == org_id)
    )).scalars().first()
    if club is None:
        return None, None
    pipeline = await crm_service.ensure_platform_pipeline(session)
    deal = await crm_service._last_attributed_deal_for_club(session, pipeline.id, club.id)
    return club, (deal.commission_rep_user_id if deal else None)


async def record_payment_commission(session: AsyncSession, row) -> None:
    """Stamp a recorded Stripe invoice with what it earned, if anything.

    Called from the invoice webhook once the payment is confirmed. Everything
    is written onto the invoice row itself and never recomputed, which is what
    makes the ledger auditable and what stops a later rate change rewriting
    history. Idempotent: a replayed webhook re-stamps the same figures, and an
    invoice already stamped for a rep is not re-attributed if the club's
    attribution later moves.

    Best-effort by design — a commission bookkeeping failure must never fail
    the webhook that recorded the payment itself."""
    try:
        if row.status != "paid":
            return
        kind = COMMISSIONABLE_BILLING_REASONS.get(row.billing_reason or "")
        amount = int(row.amount_ex_tax_cents or 0)
        if kind is None or amount <= 0:
            # A renewal, a credit note, or an invoice we cannot price. Left
            # unstamped rather than stamped at zero, so "earns nothing" and
            # "not yet assessed" stay distinguishable.
            return
        if row.commission_rep_user_id is not None and row.commission_cents is not None:
            return
        _, rep_id = await _club_and_rep_for_org(session, row.organisation_id)
        if rep_id is None:
            return
        rates = await load_rates(session)
        rate = rate_for(rates, [str(rep_id)])
        row.commission_rep_user_id = rep_id
        row.commission_rate_percent = rate
        row.commission_cents = commission_cents(amount, rate)
        row.commission_kind = kind
    except Exception:  # noqa: BLE001
        logger.exception("commission: could not stamp invoice %s", getattr(row, "id", None))


def _paid_at(inv: BillingInvoice):
    """When a payment landed, for filing it into a period. ``period_start`` is
    the invoice's own billing period, which for an initial or add-on invoice
    is the moment it was raised; ``created_at`` is the fallback for a row that
    somehow carries neither."""
    when = inv.period_start or inv.created_at
    if when is not None and when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return when


async def earned_rows(session: AsyncSession):
    """Every payment that has earned somebody something."""
    return (await session.execute(
        select(BillingInvoice).where(
            BillingInvoice.status == "paid",
            BillingInvoice.commission_kind.isnot(None),
            BillingInvoice.commission_rep_user_id.isnot(None),
        )
    )).scalars().all()


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


def deal_state(deal: CrmDeal, stage) -> str:
    """'won' | 'lost' | 'open', taken from the STAGE the deal is sitting in.

    ``crm_deals.status`` is derived FROM the stage everywhere it is written
    (``move_stage``, ``close_deal``, ``create_deal``), so the two normally
    agree. Where they don't, the stage is the one a reader sees — on the
    pipeline board and in this very table — and a deal listed under "deals
    won" has to be one that is actually sitting in Won. Reported live: a deal
    showing Stage "Trial" appearing in a won list, which is a contradiction
    the reader cannot resolve. Falling back to ``status`` only when the stage
    can't be resolved at all keeps a deal on some pipeline other than the
    platform one from vanishing entirely."""
    if stage is not None:
        return "won" if stage.is_won else "lost" if stage.is_lost else "open"
    return deal.status


def _blank_row() -> dict:
    return {
        "clubs_attributed": 0,
        "open_deals": 0,
        "pipeline_value_cents": 0,
        "weighted_pipeline_value_cents": 0,
        "forecast_commission_cents": 0,
        "weighted_forecast_commission_cents": 0,
        "paid_invoices": 0,
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
        stage = stage_by_id.get(d.stage_id)
        state = deal_state(d, stage)
        if state == "open":
            prob = crm_service.effective_probability(d, stage) or 0
            row["open_deals"] += 1
            row["pipeline_value_cents"] += value
            row["weighted_pipeline_value_cents"] += round(value * prob / 100)
        # A WON deal is deliberately NOT counted here. Earned commission comes
        # from a confirmed Stripe payment (see earned_rows below), not from a
        # deal's stage — a stage is a human judgement, a payment is a fact.

    # What has actually been PAID BY CLUBS, which is what earns commission.
    for inv in await earned_rows(session):
        account = str(inv.commission_rep_user_id)
        entry = by_account.get(account)
        if pinned_ids is not None and account not in pinned_ids:
            continue
        if entry is not None:
            key, name = entry["id"], entry["name"]
        else:
            key, name = account, "Former rep"
        row = _bucket(key, name, rates["default"] if entry is None
                      else rate_for(rates, entry.get("ids") or [entry["id"]]))
        row["paid_invoices"] += 1
        row["won_value_cents"] += int(inv.amount_ex_tax_cents or 0)
        row["commission_earned_cents"] += int(inv.commission_cents or 0)

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
    earned = await earned_rows(session)

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

        for inv in earned:
            when = _paid_at(inv)
            if when is None or not (start <= when < end):
                continue
            account = str(inv.commission_rep_user_id)
            if pinned_ids is not None and account not in pinned_ids:
                continue
            entry = by_account.get(account)
            rkey = entry["id"] if entry else account
            name = entry["name"] if entry else "Former rep"
            _row(rkey, name)["earned_cents"] += int(inv.commission_cents or 0)

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

async def rep_payments(session: AsyncSession, *, rep_user_id: str, pinned_rep_id=None) -> dict:
    """The PAYMENTS behind one rep's earned figure.

    Each row is a confirmed Stripe invoice with the rate and commission that
    were stamped on it when it was paid — the ledger, not a recalculation, so
    what this lists is exactly what the table totals."""
    entries = await _rep_entries(session)
    by_account = _entry_of_account(entries)
    if pinned_rep_id is not None:
        rep_user_id = str(pinned_rep_id)
    entry = by_account.get(str(rep_user_id))
    wanted = set(entry["ids"]) if entry else {str(rep_user_id)}

    rows = [i for i in await earned_rows(session)
            if str(i.commission_rep_user_id) in wanted]
    org_ids = {i.organisation_id for i in rows}
    orgs = {o.id: o for o in (await session.execute(
        select(Organisation).where(Organisation.id.in_(org_ids))
    )).scalars().all()} if org_ids else {}
    clubs = {c.existing_org_id: c for c in (await session.execute(
        select(MarketingClub).where(MarketingClub.existing_org_id.in_(org_ids))
    )).scalars().all()} if org_ids else {}

    out = []
    for i in rows:
        club = clubs.get(i.organisation_id)
        org = orgs.get(i.organisation_id)
        when = _paid_at(i)
        out.append({
            "invoice_id": str(i.id),
            "club_name": (club.name if club else None) or (org.name if org else None) or "Unknown club",
            "kind": i.commission_kind,
            "billing_reason": i.billing_reason,
            "line_items": i.line_items or [],
            "amount_cents": int(i.amount_ex_tax_cents or 0),
            "rate_percent": float(i.commission_rate_percent or 0),
            "commission_cents": int(i.commission_cents or 0),
            "paid_on": when.date().isoformat() if when else None,
            "hosted_invoice_url": i.hosted_invoice_url,
        })
    out.sort(key=lambda r: (r["paid_on"] or "", r["club_name"].lower()), reverse=True)
    return {"payments": out, "count": len(out)}


async def rep_deals(session: AsyncSession, *, rep_user_id: str, status: str = "open",
                    pinned_rep_id=None) -> dict:
    """The OPEN deals behind one rep's forecast figure.

    Re-runs the very predicates ``commission_report`` used rather than a query
    shaped like them, so a row reading five deals can never open four — the
    rule the Sales Performance drill-downs already follow. Only 'open' is
    answerable here: what has been EARNED is a list of payments, not of deals
    (see rep_payments).
    """
    if status != "open":
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
             if deal_state(d, stage_by_id.get(d.stage_id)) == status and _mine(d)]

    club_by_id = await crm_service.clubs_by_ids(session, (d.marketing_club_id for d in deals))
    out = []
    for d in deals:
        club: Optional[MarketingClub] = club_by_id.get(d.marketing_club_id)
        value = crm_service.effective_value_cents(d)
        stage = stage_by_id.get(d.stage_id)
        prob = crm_service.effective_probability(d, stage) or 0
        rate = live
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
