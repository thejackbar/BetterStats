"""Merged seasons in the football silo.

A football season is one PlayHQ competition's season ("VAFA 2026",
"VAFA Juniors 2026"), so one playing year can arrive as several rows. A club
merges them the same way cricket does, through ``season_aliases`` (a soft map,
no row rewritten), and every season-filtered football read expands the picked
season to its whole group through ``season_group``.

The alias maps themselves are cricket's (services/season_aliases.py): the table
and its rules are the same, so the two sports cannot disagree about what a
merge means.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.season_aliases import load_active_alias_map, load_reverse_alias_map


async def season_group(db: AsyncSession, org_id, season_id) -> list[uuid.UUID]:
    """The picked season plus every season merged with it, canonical first.

    A bookmarked alias id resolves to its canonical first, so a link to a
    season that has since been merged still shows the whole year. Returned as
    UUIDs so asyncpg types an ``= ANY(:season)`` bind as uuid[].
    """
    rev = await load_reverse_alias_map(db, org_id)
    canon = rev.get(str(season_id), str(season_id))
    fwd = await load_active_alias_map(db, org_id)
    return [uuid.UUID(s) for s in [canon, *fwd.get(canon, [])]]


async def canonical_map(db: AsyncSession, org_id) -> dict[str, str]:
    """``{alias season id: canonical season id}`` for folding rows."""
    return await load_reverse_alias_map(db, org_id)
