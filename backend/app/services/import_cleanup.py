"""Deciding whether an import-created player can be deleted.

BetterImport's commit mints a real ``players`` row for every "add as new
player" name in an uploaded sheet. When that batch is undone the imported rows
go, but the minted player used to stay behind — so a mis-mapped upload (e.g. a
column of bare surnames read as names) survived its own undo and clogged the
club's Players page with empty records.

The rule here: a player the import created may be deleted by the undo ONLY
when nothing real has attached to them since. "Real" means anything a person
entered or the sync wrote — stats rows from any source, a membership, votes,
a lineup, a photo, a synced identity. Derivative rows are deliberately NOT
blocking (``import_effective_deltas`` and ``milestones`` are recomputed from
whatever truth remains; ``player_name_aliases``/``phq_id_suggestions``/
``player_sync_requests``/``sync_runs`` are bookkeeping) — those cascade away
with the player.

Shared by routers/imports.py's two undo endpoints (which know the exact
players via ``players.import_batch_id``, migration 234) and
``app.scripts.purge_import_only_players`` (the retroactive cleanup for
batches committed before the marker existed).
"""
from __future__ import annotations

import uuid
from typing import Iterable

from sqlalchemy import bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession

# (human label, table, column) — one row here means the player carries real
# club data and must be kept. Tables are fixed strings from this list only,
# never caller input.
BLOCKING_REFS: list[tuple[str, str, str]] = [
    ("imported stats", "imported_stats", "player_id"),
    ("season stats", "player_season_stats", "player_id"),
    ("per-grade season stats", "player_season_grade_stats", "player_id"),
    ("batting innings", "batting_innings", "player_id"),
    ("bowling spells", "bowling_spells", "player_id"),
    ("fielding stats", "fielding_stats", "player_id"),
    ("game appearances", "game_appearances", "player_id"),
    ("bowler wickets", "bowler_wickets", "bowler_id"),
    ("catches credited", "bowler_wickets", "fielder_id"),
    ("fall of wickets", "fall_of_wickets", "player_id"),
    ("partnerships", "partnerships", "batter1_id"),
    ("partnerships", "partnerships", "batter2_id"),
    ("manual batting", "manual_batting_innings", "player_id"),
    ("manual bowling", "manual_bowling_spells", "player_id"),
    ("manual fielding", "manual_fielding_stats", "player_id"),
    ("manual bowler wickets", "manual_bowler_wickets", "bowler_id"),
    ("manual fall of wickets", "manual_fall_of_wickets", "player_id"),
    ("manual partnerships", "manual_partnerships", "batter1_id"),
    ("manual partnerships", "manual_partnerships", "batter2_id"),
    ("partnership records", "manual_partnership_records", "batter1_id"),
    ("partnership records", "manual_partnership_records", "batter2_id"),
    ("season adjustments", "manual_season_adjustments", "player_id"),
    ("career adjustments", "manual_career_adjustments", "player_id"),
    ("achievements", "player_achievements", "player_id"),
    ("honour board entries", "club_honour_entries", "player_id"),
    ("membership record", "fee_members", "player_id"),
    ("family links", "family_members", "player_id"),
    ("squad membership", "team_members", "player_id"),
    ("saved lineups", "fixture_lineups", "player_id"),
    ("availability answers", "player_availability", "player_id"),
    ("availability periods", "player_availability_periods", "player_id"),
    ("vote ballots cast", "vote_ballots", "voter_player_id"),
    ("votes received", "vote_ballot_picks", "player_id"),
    ("net attendance", "net_attendance", "player_id"),
    ("comms contact", "comms_contacts", "player_id"),
    ("CRM record", "crm_people", "player_id"),
    ("merch movements", "merch_movements", "player_id"),
    ("fantasy squad", "fantasy_squad_players", "player_id"),
    ("fantasy pool", "fantasy_pool_players", "player_id"),
    ("fantasy draft picks", "fantasy_draft_picks", "player_id"),
    ("merge history", "merge_logs", "keep_player_id"),
    ("merge history", "merge_logs", "removed_player_id"),
]

# Tables found absent this process lifetime (e.g. a stubbed local harness
# without the raw-SQL lifespan tables) — cached purely to skip repeat lookups.
BLOCKING_REFS_MISSING: set[str] = set()

# A player whose own row shows human/sync investment is kept regardless of
# what the reference tables say. grassroots_id/playhq_id mean a synced
# identity — an import-created player never has one, so a non-NULL value here
# is a hard stop whatever else looks empty.
_PROFILE_SQL = """
    SELECT id,
           (grassroots_id IS NOT NULL OR playhq_id IS NOT NULL)     AS synced,
           (display_name_override IS NOT NULL OR photo_url IS NOT NULL
             OR photo_data IS NOT NULL OR claim_note IS NOT NULL
             OR email IS NOT NULL OR phone IS NOT NULL
             OR squad_team_id IS NOT NULL
             OR COALESCE(jsonb_array_length(skill_positions), 0) > 0) AS edited
    FROM players
    WHERE organisation_id = :org AND id IN :pids
"""


async def _table_exists(db: AsyncSession, table: str) -> bool:
    return (await db.execute(
        text("SELECT to_regclass(:t)"), {"t": f"public.{table}"}
    )).scalar() is not None


async def deletable_players(
    db: AsyncSession, org_id, player_ids: Iterable,
) -> tuple[list[uuid.UUID], dict[uuid.UUID, list[str]]]:
    """Partition candidate players into (safe to delete, {pid: why kept}).

    Callers pass players they already believe were import-created; this
    re-checks everything anyway — a candidate with a synced identity, an
    edited profile, or a row in any BLOCKING_REFS table is kept, with the
    reasons named so they can be reported rather than silently skipped.
    """
    pids = [p if isinstance(p, uuid.UUID) else uuid.UUID(str(p)) for p in player_ids]
    if not pids:
        return [], {}

    reasons: dict[uuid.UUID, list[str]] = {}

    def _block(pid: uuid.UUID, why: str) -> None:
        rs = reasons.setdefault(pid, [])
        if why not in rs:
            rs.append(why)

    profile = (await db.execute(
        text(_PROFILE_SQL).bindparams(bindparam("pids", expanding=True)),
        {"org": str(org_id), "pids": pids},
    )).mappings().all()
    found = set()
    for row in profile:
        found.add(row["id"])
        if row["synced"]:
            _block(row["id"], "synced identity (grassroots/playhq id)")
        if row["edited"]:
            _block(row["id"], "profile details have been edited")
    # A candidate not in this org (or already gone) is never deletable here.
    for pid in pids:
        if pid not in found:
            _block(pid, "not found in this club")

    checked: set[str] = set()
    for label, table, col in BLOCKING_REFS:
        if table not in checked:
            checked.add(table)
            if not await _table_exists(db, table):
                # Missing on this deployment (e.g. a stubbed local harness
                # without the raw-SQL lifespan tables) — nothing to block on.
                BLOCKING_REFS_MISSING.add(table)
        if table in BLOCKING_REFS_MISSING:
            continue
        hits = (await db.execute(
            text(f"SELECT DISTINCT {col} FROM {table} WHERE {col} IN :pids")  # noqa: S608 — fixed strings from BLOCKING_REFS
            .bindparams(bindparam("pids", expanding=True)),
            {"pids": pids},
        )).scalars().all()
        for pid in hits:
            _block(pid, label)

    deletable = [p for p in pids if p not in reasons]
    return deletable, reasons


async def delete_players(db: AsyncSession, org_id, player_ids: list[uuid.UUID]) -> int:
    """Delete the given players (org-scoped). Only call with ids that came
    back deletable from ``deletable_players`` in the same transaction —
    derivative rows (aliases, deltas, milestones) cascade away with them."""
    if not player_ids:
        return 0
    res = await db.execute(
        text("DELETE FROM players WHERE organisation_id = :org AND id IN :pids")
        .bindparams(bindparam("pids", expanding=True)),
        {"org": str(org_id), "pids": player_ids},
    )
    return res.rowcount or 0
