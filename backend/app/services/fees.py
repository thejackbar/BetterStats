"""Fee tracking service — auto-derive match-day fees + schedule seeding.

The expensive bit is `recompute_fee_match_days`: for one season it reads every
GameAppearance, ensures a fee_member / fee_member_season exists for each
appearing player, and upserts a fee_match_days row per (member-season, game).
It runs after each weekly sync and on demand from the admin UI.

Money never depends on format here — match fee = days_played × tier rate, and
the tier lives on the member-season. Format only decides how many days a game
contributes (two-day = 2) and which report bucket it falls in.
"""
from __future__ import annotations

import logging
import re
import uuid
from decimal import Decimal
from difflib import SequenceMatcher
from typing import Optional

from sqlalchemy import select, func

from app.models.db import (
    async_session_maker,
    Season, Grade, Game, Player, GameAppearance,
    FeeSchedule, FeeMember, FeeMemberSeason, FeeMatchDay, FeePayment,
)

logger = logging.getLogger(__name__)


# ── Free-text → member matching ─────────────────────────────────────────────
# Shared by the bank-statement CSV import and the Square sale import — both
# hand this a loose description (a bank ref, a Square buyer name/note) and get
# back a 0..1 confidence against a member's name.

_NOISE_RE = re.compile(r"\b(membership|match\s*fees?|fees?|payment|transfer|trf|eft|cba|nab|anz|st\s*george|deposit|to|from|ref|reference|account|acct)\b", re.I)


def clean_description(s: str) -> str:
    s = (s or "").lower()
    s = _NOISE_RE.sub(" ", s)
    s = re.sub(r"[^a-z\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def match_score(cleaned_desc: str, member_name: str) -> float:
    """0..1 confidence the description belongs to this member.

    Combines:
      - SequenceMatcher ratio between cleaned description and member name
        (forward + 'Surname, First' → 'First Surname' flipped — bank refs and
        Square buyer names usually go first-last even though the sheet stores
        names as 'Surname, First').
      - Token overlap bonus: every surname/firstname token from the member
        name that appears verbatim in the description adds 0.15, capped at 1.
    """
    if not cleaned_desc or not member_name:
        return 0.0
    name_lc = member_name.lower()
    if "," in name_lc:
        parts = [p.strip() for p in name_lc.split(",", 1)]
        flipped = (parts[1] + " " + parts[0]).strip()
    else:
        flipped = name_lc
    name_clean = re.sub(r"[^a-z\s]", " ", flipped)
    name_clean = re.sub(r"\s+", " ", name_clean).strip()
    base = max(
        SequenceMatcher(None, cleaned_desc, name_clean).ratio(),
        SequenceMatcher(None, cleaned_desc, name_lc).ratio(),
    )
    tokens = [t for t in name_clean.split() if len(t) >= 3]
    overlap = sum(1 for t in tokens if t in cleaned_desc)
    return min(1.0, base + 0.15 * overlap)


# How many days each format contributes by default. Two-day defaults to 2
# (the club's "Default to 2, override down" rule) since BetterStats stores a
# two-day match as a single game and can't tell if a player missed a day.
FORMAT_DEFAULT_DAYS = {
    "two_day": Decimal("2"),
    "one_day": Decimal("1"),
    "t20": Decimal("1"),
    "women": Decimal("1"),
}


def derive_fee_format(grade_fee_format: str | None, match_format: str | None):
    """Resolve a game's (fee_format, default_days).

    A grade-level override wins; otherwise we map games.match_format. Returns
    (None, None) when the grade is explicitly excluded from fees.
    """
    ff = (grade_fee_format or "").strip().lower()
    if ff == "exclude":
        return None, None
    if ff in FORMAT_DEFAULT_DAYS:
        return ff, FORMAT_DEFAULT_DAYS[ff]

    mf = (match_format or "").strip().lower()
    if "two" in mf:  # "Two Day+", "Two Day"
        return "two_day", FORMAT_DEFAULT_DAYS["two_day"]
    if "t20" in mf or "twenty" in mf:
        return "t20", FORMAT_DEFAULT_DAYS["t20"]
    # Everything else (One Day, blank, unknown) is treated as a single day.
    return "one_day", FORMAT_DEFAULT_DAYS["one_day"]


def allocate_match_days(charges, match_paid, waived=None):
    """Spread a member's total match-fee money across their match days, oldest
    game first — the BetterFees auto-allocation.

    `charges` is the per-game fee (days_played × tier rate) in settle order
    (oldest game first). `match_paid` is the sum of the member's match_day
    payments. Each game is paid in full while the money lasts; the first game
    the money can't fully cover is 'partial' (with whatever is left), the rest
    'unpaid'. A $0 game (rate $0 / no tier) is 'na' and never consumes money.

    `waived` (optional) is a parallel list of bools — a waived game is settled
    without money (status 'waived'), so it consumes none of `match_paid`; the
    remaining money flows on to the next unwaived game. Waiving always wins over
    the $0 'na' case so an explicit waive is visible.

    Returns (rows, credit):
      rows   — list parallel to `charges` of (status, amount_covered),
               status ∈ {'paid', 'partial', 'unpaid', 'na', 'waived'}.
      credit — money left over once every game is fully covered (the member is
               'in the Green'); Decimal('0') otherwise.
    """
    remaining = Decimal(str(match_paid or 0))
    waived = waived or [False] * len(charges)
    rows = []
    for charge, is_waived in zip(charges, waived):
        c = Decimal(str(charge or 0))
        if is_waived:
            rows.append(("waived", Decimal("0")))
        elif c <= 0:
            rows.append(("na", Decimal("0")))
        elif remaining >= c:
            rows.append(("paid", c))
            remaining -= c
        elif remaining > 0:
            rows.append(("partial", remaining))
            remaining = Decimal("0")
        else:
            rows.append(("unpaid", Decimal("0")))
    credit = remaining if remaining > 0 else Decimal("0")
    return rows, credit


async def latest_season_id(session, organisation_id):
    """The club's most recent season (by year, then name) — the fees season."""
    row = await session.execute(
        select(Season.id)
        .where(Season.organisation_id == organisation_id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


def _f(x) -> float:
    return float(x) if x is not None else 0.0


def _financials(schedule: Optional[FeeSchedule], match_days: float, paid: Optional[dict] = None,
                waived_days: float = 0.0) -> dict:
    """Build the canonical financials dict.

    Status rules mirror the spreadsheet:
      - no tier            → 'needs_tier'        (don't try to compute fees)
      - complimentary tier → 'financial'          (no money owed regardless)
      - upfront tier       → financial iff membership paid (match fee is $0)
      - standard tier      → financial iff membership + match fees paid

    `waived_days` is the days_played belonging to waived games. They are removed
    from `match_fee_payable` (so the member reads Financial without owing them)
    and surfaced separately as `match_fee_waived` — waived fees are forgiven, NOT
    money received, so they never touch the paid/credit pots. `match_days` stays
    the total (incl. waived) for display.

    'No games played' is a derived UI flag, not a status — it only suppresses
    the follow-up nudge for someone who never showed up.

    Moved here from routers/fees.py (extracted, not duplicated) so both the
    admin member-detail endpoint and the member-portal "my fees" view compute
    from the exact same function — see member_financial_snapshot below.
    """
    membership_payable = _f(schedule.membership_amount) if schedule else 0.0
    rate = _f(schedule.match_day_rate) if schedule else 0.0
    billable_days = max(match_days - (waived_days or 0.0), 0.0)
    match_fee_waived = round((waived_days or 0.0) * rate, 2)
    match_fee_payable = round(billable_days * rate, 2)
    paid = paid or {"membership": 0.0, "match_day": 0.0}
    membership_paid = float(paid.get("membership", 0.0))
    match_fee_paid = float(paid.get("match_day", 0.0))
    membership_outstanding = round(max(membership_payable - membership_paid, 0.0), 2)
    match_fee_outstanding = round(max(match_fee_payable - match_fee_paid, 0.0), 2)
    total_outstanding = round(membership_outstanding + match_fee_outstanding, 2)

    # Credit ('in the Green') — surplus on each bucket. Membership and match-fee
    # pots are kept separate (club preference), so over-paying one never masks
    # money still owed on the other. No tier means we can't say what's owed, so
    # we don't claim any credit.
    membership_credit = round(max(membership_paid - membership_payable, 0.0), 2) if schedule is not None else 0.0
    match_fee_credit = round(max(match_fee_paid - match_fee_payable, 0.0), 2) if schedule is not None else 0.0
    credit = round(membership_credit + match_fee_credit, 2)

    if schedule is None:
        status = "needs_tier"
    elif schedule.payment_type == "complimentary":
        status = "financial"
    elif total_outstanding <= 0:
        status = "financial"
    else:
        status = "non_financial"

    return {
        "tier": schedule.name if schedule else None,
        "payment_type": schedule.payment_type if schedule else None,
        "membership_payable": membership_payable,
        "match_day_rate": rate,
        "match_days": match_days,
        "waived_days": round(waived_days or 0.0, 1),
        "match_fee_waived": match_fee_waived,
        "match_fee_payable": match_fee_payable,
        "total_payable": round(membership_payable + match_fee_payable, 2),
        "membership_paid": round(membership_paid, 2),
        "match_fee_paid": round(match_fee_paid, 2),
        "total_paid": round(membership_paid + match_fee_paid, 2),
        "membership_outstanding": membership_outstanding,
        "match_fee_outstanding": match_fee_outstanding,
        "total_outstanding": total_outstanding,
        "membership_credit": membership_credit,
        "match_fee_credit": match_fee_credit,
        "credit": credit,
        "in_credit": credit > 0,
        "status": status,
        "needs_tier": schedule is None,
        "no_games_played": (match_days == 0 and membership_payable == 0),
    }


async def member_financial_snapshot(session, organisation_id, member_id, season_id=None) -> Optional[dict]:
    """Read-only fee snapshot for one member — the member-portal "my fees"
    view. Deliberately separate from routers/fees.py::get_member's own inline
    query (which stays untouched to avoid any regression risk to the existing
    admin endpoint); this shares only the pure financial math (_financials,
    allocate_match_days) so both give the identical numbers.

    Returns None if the member doesn't belong to this org, or has no
    fee_member_season for the resolved season (a fresh/never-tiered member —
    the portal shows "not set up yet" in that case)."""
    member = await session.get(FeeMember, member_id)
    if member is None or member.organisation_id != organisation_id:
        return None
    season_id = season_id or await latest_season_id(session, organisation_id)
    if season_id is None:
        return None
    ms = (await session.execute(
        select(FeeMemberSeason).where(
            FeeMemberSeason.member_id == member.id, FeeMemberSeason.season_id == season_id,
        )
    )).scalar_one_or_none()
    if ms is None:
        return None

    schedule = await session.get(FeeSchedule, ms.fee_schedule_id) if ms.fee_schedule_id else None

    pay_rows = (await session.execute(
        select(FeePayment).where(FeePayment.member_season_id == ms.id)
        .order_by(FeePayment.paid_at.desc().nullslast(), FeePayment.created_at.desc())
    )).scalars().all()
    paid_totals = {"membership": 0.0, "match_day": 0.0}
    for p in pay_rows:
        paid_totals[p.kind] = paid_totals.get(p.kind, 0.0) + _f(p.amount)

    rows = (await session.execute(
        select(FeeMatchDay, Game, Grade)
        .outerjoin(Game, FeeMatchDay.game_id == Game.id)
        .outerjoin(Grade, Game.grade_id == Grade.id)
        .where(FeeMatchDay.member_season_id == ms.id)
        .order_by(FeeMatchDay.played_at.nullslast(), FeeMatchDay.id)
    )).all()
    rate = Decimal(str(_f(schedule.match_day_rate))) if schedule else Decimal("0")
    charges = [
        (Decimal(str(_f(e.days_played))) * rate) if e.days_played is not None else Decimal("0")
        for e, _game, _grade in rows
    ]
    waived_flags = [e.waived_at is not None for e, _game, _grade in rows]
    alloc, _credit = allocate_match_days(charges, paid_totals.get("match_day", 0.0), waived_flags)

    total_days = 0.0
    waived_days = 0.0
    match_days_out = []
    for (e, game, grade), charge, (st, covered) in zip(rows, charges, alloc):
        total_days += _f(e.days_played)
        if e.waived_at is not None:
            waived_days += _f(e.days_played)
        match_days_out.append({
            "played_at": e.played_at.isoformat() if e.played_at else None,
            "charge": round(float(charge), 2),
            "status": st,
            "amount_covered": round(float(covered), 2),
            "waived": e.waived_at is not None,
            "grade": grade.display_name if grade else None,
            "match": f"{game.home_team} v {game.away_team}" if game else None,
        })

    fin = _financials(schedule, total_days, paid_totals, waived_days)
    return {
        "member": {
            "id": str(member.id), "full_name": member.full_name,
            "email": member.email, "mobile": member.mobile,
            "is_life_member": member.is_life_member, "is_honorary": member.is_honorary,
        },
        "season_id": str(season_id),
        "financials": fin,
        "match_days": match_days_out,
    }


async def recompute_fee_match_days(organisation_id: str, season_id: str | None = None) -> dict:
    """Rebuild auto-derived match-day rows for one season.

    - Auto-creates fee_members (linked to the stats player) + fee_member_seasons
      for anyone who appears in a game and isn't tracked yet. New members land
      with no tier (the "Needs tier" review queue) unless their carry-forward
      current_tier matches a schedule row this season.
    - Upserts one fee_match_days row per (member-season, game). Rows an admin
      has overridden (auto_derived=False) are never touched.
    - Deletes stale auto rows (player withdrew, or grade newly excluded).
    """
    async with async_session_maker() as session:
        org_id = organisation_id if isinstance(organisation_id, uuid.UUID) else uuid.UUID(str(organisation_id))

        if season_id is None:
            sid = await latest_season_id(session, org_id)
        else:
            sid = season_id if isinstance(season_id, uuid.UUID) else uuid.UUID(str(season_id))
        if sid is None:
            return {"season_id": None, "members_created": 0, "entries_upserted": 0, "entries_deleted": 0}

        # Grades (with fee_format overrides) + games for the season.
        grades = {
            g.id: g for g in (
                await session.execute(select(Grade).where(Grade.season_id == sid))
            ).scalars().all()
        }
        games = (
            await session.execute(
                select(Game).join(Grade, Game.grade_id == Grade.id).where(Grade.season_id == sid)
            )
        ).scalars().all()

        game_meta: dict = {}  # game_id -> (fee_format, default_days, played_at)
        for g in games:
            grade = grades.get(g.grade_id)
            ff, days = derive_fee_format(grade.fee_format if grade else None, g.match_format)
            if ff is None:
                continue  # excluded grade
            game_meta[g.id] = (ff, days, g.played_at)

        if not game_meta:
            # Still clean up any stale auto rows from a previous run.
            await _delete_stale_auto_entries(session, sid, valid_keys=set())
            await session.commit()
            return {"season_id": str(sid), "members_created": 0, "entries_upserted": 0, "entries_deleted": 0}

        game_ids = list(game_meta.keys())

        # Appearances across those games (only our club's players have rows).
        appearances = (
            await session.execute(
                select(GameAppearance).where(GameAppearance.game_id.in_(game_ids))
            )
        ).scalars().all()

        player_ids = {a.player_id for a in appearances}
        if not player_ids:
            await _delete_stale_auto_entries(session, sid, valid_keys=set())
            await session.commit()
            return {"season_id": str(sid), "members_created": 0, "entries_upserted": 0, "entries_deleted": 0}

        players = {
            p.id: p for p in (
                await session.execute(select(Player).where(Player.id.in_(player_ids)))
            ).scalars().all()
        }

        # Schedule names → id for carry-forward tier defaulting.
        schedule_by_name = {
            (s.name or "").strip().lower(): s.id for s in (
                await session.execute(select(FeeSchedule).where(FeeSchedule.season_id == sid))
            ).scalars().all()
        }

        # Existing members for these players.
        member_by_player = {
            m.player_id: m for m in (
                await session.execute(
                    select(FeeMember).where(
                        FeeMember.organisation_id == org_id,
                        FeeMember.player_id.in_(player_ids),
                    )
                )
            ).scalars().all()
        }

        members_created = 0
        for pid in player_ids:
            if pid in member_by_player:
                continue
            player = players.get(pid)
            if player is None:
                continue
            m = FeeMember(
                id=uuid.uuid4(),
                organisation_id=org_id,
                player_id=pid,
                full_name=player.display_name,
            )
            session.add(m)
            member_by_player[pid] = m
            members_created += 1
        await session.flush()

        # Existing member-seasons for this season.
        member_ids = [m.id for m in member_by_player.values()]
        ms_by_member = {
            ms.member_id: ms for ms in (
                await session.execute(
                    select(FeeMemberSeason).where(
                        FeeMemberSeason.season_id == sid,
                        FeeMemberSeason.member_id.in_(member_ids),
                    )
                )
            ).scalars().all()
        }
        for m in member_by_player.values():
            if m.id in ms_by_member:
                continue
            tier_id = schedule_by_name.get((m.current_tier or "").strip().lower()) if m.current_tier else None
            ms = FeeMemberSeason(
                id=uuid.uuid4(),
                member_id=m.id,
                season_id=sid,
                organisation_id=org_id,
                fee_schedule_id=tier_id,
            )
            session.add(ms)
            ms_by_member[m.id] = ms
        await session.flush()

        # Existing match-day rows for this season, keyed by (member_season, game).
        ms_ids = [ms.id for ms in ms_by_member.values()]
        existing = {
            (e.member_season_id, e.game_id): e for e in (
                await session.execute(
                    select(FeeMatchDay).where(FeeMatchDay.member_season_id.in_(ms_ids))
                )
            ).scalars().all()
        }

        entries_upserted = 0
        valid_keys: set = set()
        for a in appearances:
            member = member_by_player.get(a.player_id)
            if member is None:
                continue
            ms = ms_by_member.get(member.id)
            if ms is None:
                continue
            ff, days, played_at = game_meta[a.game_id]
            key = (ms.id, a.game_id)
            valid_keys.add(key)
            row = existing.get(key)
            if row is None:
                session.add(FeeMatchDay(
                    id=uuid.uuid4(),
                    member_season_id=ms.id,
                    game_id=a.game_id,
                    played_at=played_at,
                    fee_format=ff,
                    days_played=days,
                    auto_derived=True,
                ))
                entries_upserted += 1
            elif row.auto_derived and row.paid_payment_id is None:
                # Keep auto rows in sync with the latest format/date mapping —
                # but freeze them once paid (we don't want a re-sync to silently
                # increase the days a member already has a payment for).
                changed = False
                if row.fee_format != ff:
                    row.fee_format = ff; changed = True
                if row.days_played != days:
                    row.days_played = days; changed = True
                if row.played_at != played_at:
                    row.played_at = played_at; changed = True
                if changed:
                    entries_upserted += 1
            # else: admin-overridden or already paid — leave untouched.

        entries_deleted = await _delete_stale_auto_entries(session, sid, valid_keys)
        await session.commit()

        logger.info(
            "Fee recompute org=%s season=%s: +%d members, %d entries upserted, %d stale removed",
            org_id, sid, members_created, entries_upserted, entries_deleted,
        )
        return {
            "season_id": str(sid),
            "members_created": members_created,
            "entries_upserted": entries_upserted,
            "entries_deleted": entries_deleted,
        }


async def _delete_stale_auto_entries(session, season_id, valid_keys: set) -> int:
    """Remove auto-derived rows that no longer correspond to an appearance
    (player withdrew, or grade is now excluded). Overridden rows are kept."""
    ms_ids = (
        await session.execute(
            select(FeeMemberSeason.id).where(FeeMemberSeason.season_id == season_id)
        )
    ).scalars().all()
    if not ms_ids:
        return 0
    rows = (
        await session.execute(
            select(FeeMatchDay).where(
                FeeMatchDay.member_season_id.in_(ms_ids),
                FeeMatchDay.auto_derived.is_(True),
                FeeMatchDay.paid_payment_id.is_(None),  # never auto-remove paid rows
            )
        )
    ).scalars().all()
    deleted = 0
    for r in rows:
        if (r.member_season_id, r.game_id) not in valid_keys:
            await session.delete(r)
            deleted += 1
    return deleted


# ── Default rate card ───────────────────────────────────────────────────────
# Faithful to the 2025/26 "Membership Recovery" PARMS sheet: (name,
# payment_type, membership_amount, match_day_rate). The handful of unlabelled
# match-fee-only rows in the sheet (?, ??, W?…) are intentionally omitted —
# they aren't membership tiers.
DEFAULT_SCHEDULE = [
    ("Est. M/Ship", "standard", 250, 20),
    ("Est. Upfront", "upfront", 550, 0),
    ("New Upfront", "upfront", 470, 0),
    ("New M/Ship", "standard", 200, 20),
    ("Student Upfront", "upfront", 350, 0),
    ("Student M/Ship", "standard", 150, 15),
    ("Ladies Est.", "upfront", 225, 0),
    ("Ladies New", "upfront", 185, 0),
    ("Ladies Student", "upfront", 150, 0),
    ("Venetians", "upfront", 200, 0),
    ("ICL", "standard", 0, 0),
    ("Life Member - Complimentary", "complimentary", 0, 20),
    ("LM / Sponsor - Complimentary", "complimentary", 0, 0),
    ("Sponsor - Complimentary", "complimentary", 0, 20),
    ("Complimentary Season", "complimentary", 0, 0),
    ("Fill In - Senior", "complimentary", 0, 20),
    ("Fill In - Student", "complimentary", 0, 15),
    ("Fill In - Womens", "complimentary", 0, 15),
    ("Applecross Junior", "complimentary", 0, 10),
    ("Juniors New", "standard", 100, 10),
    ("Half Season - Student", "standard", 100, 15),
    ("Half Season - Senior", "standard", 100, 20),
    ("Closed M/Ship", "left_club", 60, 0),
    ("Closed M/Ship 2", "left_club", 70, 0),
    ("Closed M/Ship 3", "left_club", 330, 0),
]


async def seed_default_schedule(session, organisation_id, season_id) -> int:
    """Insert the default rate card into a season, skipping names already there.
    Returns the number of rows created."""
    existing = {
        (s.name or "").strip().lower() for s in (
            await session.execute(select(FeeSchedule).where(FeeSchedule.season_id == season_id))
        ).scalars().all()
    }
    created = 0
    for order, (name, ptype, membership, rate) in enumerate(DEFAULT_SCHEDULE):
        if name.strip().lower() in existing:
            continue
        session.add(FeeSchedule(
            id=uuid.uuid4(),
            organisation_id=organisation_id,
            season_id=season_id,
            name=name,
            payment_type=ptype,
            membership_amount=Decimal(str(membership)),
            match_day_rate=Decimal(str(rate)),
            display_order=order,
        ))
        created += 1
    return created


# ───────────────────────────────────────────────────────────────────────────
# Who owes money
# ───────────────────────────────────────────────────────────────────────────

async def outstanding_by_member(session: AsyncSession, season_id) -> dict:
    """{member_id: outstanding} for one season, using the SAME `_financials`
    the Accounts screen reads.

    A balance is derived, never stored (see the BetterFees allocation note), so
    anything that needs "who owes money" has to run this calculation rather than
    reimplement it in SQL. Re-deriving it a second way is how the sidebar badge,
    the Today row and an audience would start disagreeing with each other.
    """
    from app.models.db import FeeMatchDay, FeeMemberSeason, FeeMember, FeePayment, FeeSchedule

    rows = (await session.execute(
        select(FeeMemberSeason, FeeMember, FeeSchedule)
        .join(FeeMember, FeeMemberSeason.member_id == FeeMember.id)
        .outerjoin(FeeSchedule, FeeMemberSeason.fee_schedule_id == FeeSchedule.id)
        .where(FeeMemberSeason.season_id == season_id)
    )).all()

    days = {ms_id: float(d) for ms_id, d in (await session.execute(
        select(FeeMatchDay.member_season_id, func.coalesce(func.sum(FeeMatchDay.days_played), 0))
        .join(FeeMemberSeason, FeeMatchDay.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id)
        .group_by(FeeMatchDay.member_season_id)
    )).all()}
    waived = {ms_id: float(d) for ms_id, d in (await session.execute(
        select(FeeMatchDay.member_season_id, func.coalesce(func.sum(FeeMatchDay.days_played), 0))
        .join(FeeMemberSeason, FeeMatchDay.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id, FeeMatchDay.waived_at.isnot(None))
        .group_by(FeeMatchDay.member_season_id)
    )).all()}
    paid: dict = {}
    for ms_id, kind, amount in (await session.execute(
        select(FeePayment.member_season_id, FeePayment.kind, func.coalesce(func.sum(FeePayment.amount), 0))
        .join(FeeMemberSeason, FeePayment.member_season_id == FeeMemberSeason.id)
        .where(FeeMemberSeason.season_id == season_id)
        .group_by(FeePayment.member_season_id, FeePayment.kind)
    )).all():
        paid.setdefault(ms_id, {"membership": 0.0, "match_day": 0.0})[kind] = float(amount)

    out = {}
    for ms, member, schedule in rows:
        fin = _financials(schedule, days.get(ms.id, 0.0), paid.get(ms.id), waived.get(ms.id, 0.0))
        out[member.id] = float(fin["total_outstanding"])
    return out


async def owing_player_ids(session: AsyncSession, org_id, season_id) -> set:
    """The player ids behind every member of this season who still owes.
    Members with no linked player drop out — an audience resolves against
    contacts, which key on the player."""
    from app.models.db import FeeMember

    balances = await outstanding_by_member(session, season_id)
    owing = {mid for mid, bal in balances.items() if bal > 0}
    if not owing:
        return set()
    rows = (await session.execute(
        select(FeeMember.player_id).where(
            FeeMember.id.in_(owing),
            FeeMember.organisation_id == org_id,
            FeeMember.player_id.isnot(None),
        )
    )).scalars().all()
    return {pid for pid in rows if pid}
