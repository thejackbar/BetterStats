"""Are two player records, offered as "the same person", more likely two different people?

The Merge Players screen lists two records with the same name as an "exact" duplicate and lets a
club Bulk Approve all of them. A name is not an identity. Mulgrave's two Luke Bennetts (a junior in a
U11 competition and an adult in first grade) were merged together on 23 July, and the adult record
then held 16 junior games.

The one signal that separates a duplicate from a namesake without any outside data is TIME. One
person is in one game on a given day (an occasional double-header aside); a duplicate record is the
SAME person under a second id, so the two records are never both active on the same date. Two
records that each have a game on the same date, in different games, are therefore very likely two
people.

Two records in the SAME game is not counted here. A duplicate made by a shared id (a per-club uuid5
beside the raw id) can hold a row in the same game for one person, and `scripts/merge_player_pair`
already refuses that case separately.

A signal, not a verdict: the screen keeps the pair out of Bulk Approve and asks for an explicit
confirmation to merge it by hand. Nothing is blocked outright.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_CLASH_SQL = """
    SELECT DISTINCT g1.played_at
    FROM game_appearances x
    JOIN games g1 ON g1.id = x.game_id
    JOIN game_appearances y ON y.player_id = CAST(:b AS UUID)
    JOIN games g2 ON g2.id = y.game_id AND g2.played_at = g1.played_at AND g2.id <> g1.id
    WHERE x.player_id = CAST(:a AS UUID) AND g1.played_at IS NOT NULL
    ORDER BY g1.played_at DESC
"""


async def same_day_clash_dates(db: AsyncSession, a, b) -> list:
    """The dates on which both players have a game, in different games (newest first)."""
    rows = await db.execute(text(_CLASH_SQL), {"a": str(a), "b": str(b)})
    return [r[0] for r in rows.all()]


def clash_message(dates: list) -> str:
    n = len(dates)
    return (
        f"These two records both have games on the same {'date' if n == 1 else 'dates'} "
        f"({n} in all, most recently {dates[0]}). One person is not in two games on one day, so "
        f"this is usually two different people who share a name, such as a junior and an adult. "
        f"Merge them only if you are sure they are the same person."
    )
