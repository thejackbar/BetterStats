"""Merge redirects that lead to a player who is no longer there.

A merge deletes the removed player and writes ``merge_logs (removed -> keep)``.
Sync reads those rows as a redirect: a scorecard or season feed that still names
the removed id is attached to the kept player instead. That only works while
the kept player exists. When it does not (the kept record was itself removed
or never survived), every row sync inserts for that id points at nothing, the
database refuses the foreign key, and the WHOLE game rolls back. The failure was
swallowed per game with no counter, so a club lost every match that named that
one person and the run still read as a success (Oak Park St Francis de Sales,
October 2026: both 1st XI and both 3rd XI games, each naming a player whose new
participant id redirected to a missing record).

``drop_dangling`` splits a redirect map into the ones that still lead somewhere
and the ones that do not, so the caller can treat a dangling id as what it is:
an id the club does not know. A game then stores without that one player, who is
matched by name or created like any other new participant.
"""
from __future__ import annotations

import uuid
from typing import Mapping

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def drop_dangling(db: AsyncSession, redirects: Mapping) -> tuple[dict, dict]:
    """``(live, dangling)`` halves of ``{removed id: kept id}``.

    Redirects are judged on their FINAL target, so resolve chains first. Keys and
    values may be ``str`` or ``UUID`` (the aggregate pass and the scorecard pass
    build different shapes); each half keeps them as they came in. One read, by a
    bound array of ids.
    """
    if not redirects:
        return {}, {}
    wanted = sorted({str(uuid.UUID(str(t))) for t in redirects.values()})
    alive = {
        r[0] for r in (await db.execute(
            text("SELECT id::text FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
            {"ids": wanted},
        )).all()
    }
    live: dict = {}
    dangling: dict = {}
    for removed, kept in redirects.items():
        (live if str(uuid.UUID(str(kept))) in alive else dangling)[removed] = kept
    return live, dangling
