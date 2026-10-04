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
    # What a club typed or a player answered about the PERSON rather than the
    # cricket: availability, who is in which squad and lineup, nets attendance,
    # family links, the alternate spellings a live feed still resolves, and the
    # contact rows the lists are built from. All of them were `ON DELETE
    # CASCADE` (or `SET NULL`, which quietly unlinks a member from their
    # player), so merging a freshly added roster record into the synced one
    # emptied the squad, the availability and the contact details with it.
    ("player_availability", "player_id", "int", ("avail_date",)),
    ("player_availability_periods", "player_id", "int", None),
    ("net_attendance", "player_id", "uuid", ("session_id",)),
    ("net_checkin_registrations", "player_id", "uuid", None),
    ("fixture_lineups", "player_id", "uuid", ("fixture_id",)),
    ("team_members", "player_id", "uuid", ("team_id",)),
    ("family_members", "player_id", "uuid", ("family_id",)),
    ("player_name_aliases", "player_id", "uuid", ("alias_key",)),
    ("comms_contacts", "player_id", "uuid", None),
    ("crm_people", "player_id", "uuid", None),
    ("fee_members", "player_id", "uuid", ("organisation_id",)),
)

# Tables whose primary key is not an `id` column: the column that identifies one
# row among this player's own (the other half of the key is the player).
_ROW_KEY = {"fixture_lineups": "fixture_id", "team_members": "team_id"}

# A row somebody decided something about (a membership with payments and a role,
# a contact who unsubscribed, a CRM link) is never deleted to settle a clash
# with the keeper's. If the keeper already holds the matching row, the removed
# side's is simply not moved and stays as it was (unlinked, by its own FK).
_NEVER_DELETE = {"fee_members", "comms_contacts", "crm_people"}

# The link tables above belong to one club. A club-to-club merge (services/
# org_merge) re-homes the source club's players into the target before merging
# them, and their rows still carry the SOURCE club's id (and its teams, its
# families). Carrying those onto a target-club player would leave rows that
# point across clubs - and fee_members' composite FK refuses them outright - so
# a row is only carried when it belongs to the keeper's own club. Anything else
# is left to go as it always did.
_OWN_CLUB = {
    "family_members": "EXISTS (SELECT 1 FROM families f WHERE f.id = r.family_id "
                      "AND f.organisation_id = :org)",
}
_OWN_CLUB_TABLES = {
    "player_availability", "player_availability_periods", "net_attendance",
    "net_checkin_registrations", "fixture_lineups", "team_members",
    "player_name_aliases", "comms_contacts", "crm_people", "fee_members",
}

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


async def carry_rows(db: AsyncSession, keep_id, remove_id, org_id=None) -> dict:
    """Move the removed player's records onto the keeper.

    `org_id` is the keeper's club. When given, the link tables that belong to a
    club (see `_OWN_CLUB`) only carry the rows that are that club's own.

    Returns `{"<table>.<column>": [ids moved]}` for the merge log, so the undo
    can hand back exactly those rows and nothing else.
    """
    moved: dict[str, list] = {}
    for table, column, id_type, unique_rest in CARRIED:
        if not await _exists(db, table):
            continue
        params = {"kid": str(keep_id), "rid": str(remove_id)}
        row_key = _ROW_KEY.get(table, "id")
        guard = ""
        if org_id is not None:
            params["org"] = str(org_id)
            if table in _OWN_CLUB_TABLES:
                guard += " AND r.organisation_id = :org"
            elif table in _OWN_CLUB:
                guard += f" AND {_OWN_CLUB[table]}"
        if unique_rest:
            # The keeper's row wins. `IS NOT DISTINCT FROM` rather than `=`
            # because part of a key can be NULL — a season adjustment with no
            # grade is the club's whole-season correction, and `=` never
            # matches it, so the collision would slip through and the move
            # would fail on the unique index.
            joins = " AND ".join(
                f"k.{c} IS NOT DISTINCT FROM r.{c}" for c in unique_rest)
            if table in _NEVER_DELETE:
                guard += (f" AND NOT EXISTS (SELECT 1 FROM {table} k "
                          f"WHERE k.{column} = :kid AND {joins})")
            else:
                await db.execute(text(
                    f"DELETE FROM {table} r USING {table} k "
                    f" WHERE r.{column} = :rid AND k.{column} = :kid AND {joins}"
                ), params)
        # RETURNING, not a SELECT then an UPDATE: the ids logged are the rows
        # that actually moved, which is fewer than the player's rows whenever
        # the guard above held one back.
        ids = (await db.execute(text(
            f"UPDATE {table} r SET {column} = :kid "
            f" WHERE r.{column} = :rid{guard} RETURNING r.{row_key}"
        ), params)).scalars().all()
        if not ids:
            continue
        # Kept in the id's own type — a JSONB round trip preserves an integer,
        # and asyncpg infers a bound array's type from its elements, so a list
        # of strings cannot be cast to int[] at the other end.
        moved[_key(table, column)] = (
            [str(i) for i in ids] if id_type == "uuid" else [int(i) for i in ids])
    return moved


async def restore_rows(db: AsyncSession, remove_id, carried: dict, keep_id=None) -> int:
    """Put the carried rows back on the re-created player. Undo's half.

    `keep_id` is needed for the tables keyed by (thing, player) rather than an
    `id`: the row to hand back is the one that thing now has under the keeper.
    """
    if not carried:
        return 0
    restored = 0
    for table, column, id_type, _unique in CARRIED:
        ids = carried.get(_key(table, column)) or []
        if not ids or not await _exists(db, table):
            continue
        typed = [str(i) for i in ids] if id_type == "uuid" else [int(i) for i in ids]
        row_key = _ROW_KEY.get(table, "id")
        params = {"pid": str(remove_id), "ids": typed}
        owner = ""
        if row_key != "id":
            if keep_id is None:
                continue
            owner = f" AND {column} = :kid"
            params["kid"] = str(keep_id)
        result = await db.execute(text(
            f"UPDATE {table} SET {column} = :pid "
            f" WHERE {row_key} = ANY(CAST(:ids AS {_CAST[id_type]})){owner}"
        ), params)
        restored += result.rowcount or 0
    return restored


def carried_summary(carried: dict) -> dict:
    """How many rows moved, per table — what the merge reports back."""
    out: dict[str, int] = {}
    for key, ids in (carried or {}).items():
        table = key.split(".")[0]
        out[table] = out.get(table, 0) + len(ids)
    return out
