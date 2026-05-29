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
import uuid
from decimal import Decimal

from sqlalchemy import select

from app.models.db import (
    async_session_maker,
    Season, Grade, Game, Player, GameAppearance,
    FeeSchedule, FeeMember, FeeMemberSeason, FeeMatchDay,
)

logger = logging.getLogger(__name__)


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


async def latest_season_id(session, organisation_id):
    """The club's most recent season (by year, then name) — the fees season."""
    row = await session.execute(
        select(Season.id)
        .where(Season.organisation_id == organisation_id)
        .order_by(Season.year.desc().nullslast(), Season.name.desc())
        .limit(1)
    )
    return row.scalar_one_or_none()


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
            elif row.auto_derived:
                # Keep auto rows in sync with the latest format/date mapping.
                changed = False
                if row.fee_format != ff:
                    row.fee_format = ff; changed = True
                if row.days_played != days:
                    row.days_played = days; changed = True
                if row.played_at != played_at:
                    row.played_at = played_at; changed = True
                if changed:
                    entries_upserted += 1
            # else: admin-overridden, leave untouched.

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
