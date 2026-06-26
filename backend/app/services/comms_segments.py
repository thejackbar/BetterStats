"""BetterComms dynamic segments — evaluate a saved query into a contact set.

A segment ``definition`` is ``{"match": "all", "rules": [{field, op, value}, ...]}``.
Rules are ANDed (``match: all``). Every rule maps to a safe, whitelisted column —
there is no raw SQL from the client. Fields span three layers:

  * contact   — tag, source (on comms_contacts)
  * player    — role, gender, squad_team (on the linked players row)
  * stat      — matches / runs / wickets / catches THIS SEASON (summed from
                player_season_stats for the club's latest season)

A player/stat rule implies the contact must be a linked player with stats, so it
naturally narrows to the squad. The send gate (sendable_where) is always applied,
so a segment can never reach an unsubscribed / bounced / suppressed address.
See docs/bettercomms-architecture.md.
"""
from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import select, func, exists
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import (
    CommsContact, EmailSuppression, Player, PlayerSeasonStats, Season,
)

# Field groups decide which joins a definition needs.
CONTACT_FIELDS = {"tag", "source"}
PLAYER_FIELDS = {"role", "gender", "squad_team"}
STAT_FIELDS = {"matches_this_season", "runs_this_season", "wickets_this_season", "catches_this_season"}
ALL_FIELDS = CONTACT_FIELDS | PLAYER_FIELDS | STAT_FIELDS

_STAT_COLUMN = {
    "matches_this_season": "matches",
    "runs_this_season": "runs",
    "wickets_this_season": "wickets",
    "catches_this_season": "catches",
}


def sendable_where(club_id):
    """The always-on send gate shared with routers/comms.py: subscribed, not
    bounced / complained / excluded per club, and not on the global suppression
    list."""
    return [
        CommsContact.organisation_id == club_id,
        CommsContact.subscribed.is_(True),
        CommsContact.bounced.is_(False),
        CommsContact.complained.is_(False),
        CommsContact.excluded.is_(False),
        ~exists().where(func.lower(EmailSuppression.email) == func.lower(CommsContact.email)),
    ]


def _num(value) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _condition(rule: dict, stats):
    field = (rule or {}).get("field")
    op = (rule or {}).get("op")
    val = (rule or {}).get("value")
    if field == "tag":
        return CommsContact.tags.contains([str(val)]) if val else None
    if field == "source":
        return CommsContact.source == str(val)
    if field == "role":
        return Player.player_role == str(val)
    if field == "gender":
        return Player.gender == str(val)
    if field == "squad_team":
        try:
            return Player.squad_team_id == uuid.UUID(str(val))
        except (ValueError, TypeError):
            return None
    if field in STAT_FIELDS and stats is not None:
        col = stats.c[_STAT_COLUMN[field]]
        n = _num(val)
        if n is None:
            return None
        if op == "lte":
            return col <= n
        if op == "eq":
            return col == n
        return col >= n  # default / "gte"
    return None


async def _current_year(session: AsyncSession, org_id) -> Optional[int]:
    return await session.scalar(
        select(func.max(Season.year)).where(
            Season.organisation_id == org_id, Season.year.isnot(None)))


async def build_query(session: AsyncSession, club, definition: dict):
    """A SELECT of the matching, sendable CommsContact rows for this club."""
    rules = [r for r in ((definition or {}).get("rules") or []) if r and r.get("field") in ALL_FIELDS]
    q = select(CommsContact).where(*sendable_where(club.id))

    if any(r["field"] in (PLAYER_FIELDS | STAT_FIELDS) for r in rules):
        q = q.join(Player, Player.id == CommsContact.player_id)

    stats = None
    if any(r["field"] in STAT_FIELDS for r in rules):
        year = await _current_year(session, club.id)
        stats = (
            select(
                PlayerSeasonStats.player_id.label("pid"),
                func.coalesce(func.sum(PlayerSeasonStats.matches), 0).label("matches"),
                func.coalesce(func.sum(PlayerSeasonStats.runs), 0).label("runs"),
                func.coalesce(func.sum(PlayerSeasonStats.wickets), 0).label("wickets"),
                func.coalesce(func.sum(PlayerSeasonStats.catches), 0).label("catches"),
            )
            .join(Season, Season.id == PlayerSeasonStats.season_id)
            .where(Season.organisation_id == club.id, Season.year == year)
            .group_by(PlayerSeasonStats.player_id)
            .subquery()
        )
        q = q.join(stats, stats.c.pid == CommsContact.player_id)

    for rule in rules:
        cond = _condition(rule, stats)
        if cond is not None:
            q = q.where(cond)
    return q


async def resolve_contacts(session: AsyncSession, club, definition: dict) -> list[CommsContact]:
    q = await build_query(session, club, definition)
    rows = (await session.execute(q.order_by(CommsContact.email))).scalars().all()
    seen, out = set(), []
    for c in rows:
        if c.email in seen:
            continue
        seen.add(c.email)
        out.append(c)
    return out


async def count(session: AsyncSession, club, definition: dict) -> int:
    q = await build_query(session, club, definition)
    # Contacts are unique per (org, email), so a row count is the contact count.
    n = await session.scalar(select(func.count()).select_from(q.subquery()))
    return int(n or 0)
