"""The rows a player merge has to carry, beyond the synced per-game tables.

`admin._merge_players_core` was written for the SYNCED career — batting
innings, bowling spells, appearances, season stats — and every table added
since has had to be remembered separately. The ones below never were, and each
of them is `ON DELETE CASCADE` on `players.id`, so removing the merged-away
player **deleted the record outright** rather than moving it:

* every manual per-game table, which is where an uploaded scorecard AND a
  whole CricketStatz import live — so merging two records of one person
  destroyed their imported career,
* the manual season and career adjustments a club typed by hand,
* `player_achievements` and `club_honour_entries`, the honour board.

Same class of bug this function has already been fixed for three times
(`bowler_wickets`, `player_season_grade_stats`, `imported_stats`) and the AFL
merge once. **A table that carries a record of what a player DID has to be
listed here.**

One definition, used by the merge and by the undo, so the two cannot disagree
about what was moved.
"""
from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# (table, column, id type, the rest of any unique key the column is part of)
#
# A unique key means the two records can each hold a row for the same game or
# season — they are the same physical person — so the removed side's duplicate
# is dropped and the keeper's kept, exactly as the synced tables already do.
CARRIED: tuple[tuple[str, str, str, Optional[tuple[str, ...]]], ...] = (
    ("manual_batting_innings", "player_id", "int",
     ("manual_game_id", "innings_number")),
    ("manual_bowling_spells", "player_id", "int", None),
    ("manual_fielding_stats", "player_id", "int", ("manual_game_id",)),
    ("manual_bowler_wickets", "bowler_id", "int", None),
    ("manual_bowler_wickets", "fielder_id", "int", None),
    ("manual_fall_of_wickets", "player_id", "int", None),
    ("manual_partnerships", "batter1_id", "int", None),
    ("manual_partnerships", "batter2_id", "int", None),
    ("manual_partnership_records", "batter1_id", "int", None),
    ("manual_partnership_records", "batter2_id", "int", None),
    ("manual_season_adjustments", "player_id", "int", ("season_id", "grade_id")),
    ("manual_career_adjustments", "player_id", "int", ("organisation_id",)),
    # No foreign key at all, so an honour is ORPHANED rather than deleted —
    # quieter, and just as lost, since every read joins `players`.
    ("player_achievements", "player_id", "int", None),
    ("club_honour_entries", "player_id", "uuid", None),
)

_CAST = {"int": "int[]", "uuid": "uuid[]"}


def _key(table: str, column: str) -> str:
    return f"{table}.{column}"


async def _exists(db: AsyncSession, table: str) -> bool:
    """Is this table in the database at all?

    Several are created by the app's lifespan in raw SQL rather than by a
    migration, so a database that has not run it yet simply has not got them.
    A merge must not fail over a table that is not there.
    """
    return bool((await db.execute(
        text("SELECT to_regclass(:t)"), {"t": table})).scalar())


async def carry_rows(db: AsyncSession, keep_id, remove_id) -> dict:
    """Move the removed player's records onto the keeper.

    Returns `{"<table>.<column>": [ids moved]}` for the merge log, so the undo
    can hand back exactly those rows and nothing else.
    """
    moved: dict[str, list] = {}
    for table, column, id_type, unique_rest in CARRIED:
        if not await _exists(db, table):
            continue
        params = {"kid": str(keep_id), "rid": str(remove_id)}
        if unique_rest:
            # The keeper's row wins. `IS NOT DISTINCT FROM` rather than `=`
            # because part of a key can be NULL — a season adjustment with no
            # grade is the club's whole-season correction, and `=` never
            # matches it, so the collision would slip through and the move
            # would fail on the unique index.
            joins = " AND ".join(
                f"k.{c} IS NOT DISTINCT FROM r.{c}" for c in unique_rest)
            await db.execute(text(
                f"DELETE FROM {table} r USING {table} k "
                f" WHERE r.{column} = :rid AND k.{column} = :kid AND {joins}"
            ), params)
        ids = (await db.execute(text(
            f"SELECT id FROM {table} WHERE {column} = :rid"), params)).scalars().all()
        if not ids:
            continue
        await db.execute(text(
            f"UPDATE {table} SET {column} = :kid WHERE {column} = :rid"), params)
        # Kept in the id's own type — a JSONB round trip preserves an integer,
        # and asyncpg infers a bound array's type from its elements, so a list
        # of strings cannot be cast to int[] at the other end.
        moved[_key(table, column)] = (
            [str(i) for i in ids] if id_type == "uuid" else [int(i) for i in ids])
    return moved


async def restore_rows(db: AsyncSession, remove_id, carried: dict) -> int:
    """Put the carried rows back on the re-created player. Undo's half."""
    if not carried:
        return 0
    restored = 0
    for table, column, id_type, _unique in CARRIED:
        ids = carried.get(_key(table, column)) or []
        if not ids or not await _exists(db, table):
            continue
        typed = [str(i) for i in ids] if id_type == "uuid" else [int(i) for i in ids]
        result = await db.execute(text(
            f"UPDATE {table} SET {column} = :pid "
            f" WHERE id = ANY(CAST(:ids AS {_CAST[id_type]}))"
        ), {"pid": str(remove_id), "ids": typed})
        restored += result.rowcount or 0
    return restored


def carried_summary(carried: dict) -> dict:
    """How many rows moved, per table — what the merge reports back."""
    out: dict[str, int] = {}
    for key, ids in (carried or {}).items():
        table = key.split(".")[0]
        out[table] = out.get(table, 0) + len(ids)
    return out
