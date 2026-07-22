"""Per-club restore — copy one organisation's data from a restored backup
bundle (living in a SCRATCH Postgres, see ops/backup/restore.sh restore-club)
into the live database, without touching any other club.

Two kinds of org-scoped table, discovered generically from information_schema
(mirrors app/services/backup_stats.py's discovery, so a newly added table is
picked up automatically — nothing here is a hardcoded table list):

  - DIRECT tables: an ``organisation_id`` column. Scoped by that column
    directly (players, settings, sponsors, fixtures, comms, merch, fees
    structure, memberships, ...).
  - GAME-scoped tables: a ``game_id`` column but no ``organisation_id`` of
    their own (batting_innings, bowling_spells, fielding_stats, ...). A game
    can be SHARED between two synced clubs (one games.id row carries BOTH
    sides' per-innings rows — see CLAUDE.md's "shared game" notes and the
    cross-club player-leak fixes), so these can NOT be scoped by game_id
    alone — that would restore/delete the OPPONENT's rows for a shared game
    too. Instead they're scoped through whichever column(s) FK-reference
    players.id (discovered from information_schema, not hardcoded), keeping
    only rows where that player belongs to the target org. A fill-in row
    (NULL player_id, free-text name — see the Jul 2026 fill-in-players work)
    has no org owner and is deliberately left untouched either way; it isn't
    counted as "restored" or "wiped".

SAFETY MODEL (this is a destructive operation on live production data, with
no staging environment — same posture CLAUDE.md calls for elsewhere):
  1. Every call defaults to dry-run (``apply=False``) — reports exactly what
     WOULD change, touches nothing.
  2. Before any real write, the club's CURRENT live rows are snapshotted to a
     JSON file on disk (not a DB column — a club's game-level data can run to
     tens of thousands of rows, too large for a JSONB blob) so the restore is
     itself undoable via ``rollback_club_restore``.
  3. Restore is DELETE-then-INSERT per table, inside ONE transaction per
     table (not one big transaction across ~70 tables — a mid-run failure
     then leaves a clearly-diagnosable partial state rather than an
     all-or-nothing lock held for the whole run).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.models.db import async_session_maker
from app.services import backup_progress

logger = logging.getLogger(__name__)

# Chunk size for progress-reporting inserts — small enough that a big table
# (batting_innings etc. can run to tens of thousands of rows for an active
# club) gives several progress updates rather than one silent multi-second
# INSERT, large enough that the round trips don't dominate the run time.
_BATCH_SIZE = 500


async def _direct_org_tables(conn) -> list[str]:
    rows = (await conn.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'organisation_id'"
    ))).all()
    return [r[0] for r in rows]


async def _game_scoped_tables(conn) -> list[str]:
    rows = (await conn.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'game_id'"
    ))).all()
    return [r[0] for r in rows if r[0] != "games"]


async def _player_fk_columns(conn) -> dict[str, list[str]]:
    """{table_name: [column names that FK-reference players.id]} — discovered
    from the live constraint catalogue, not assumed from any model file."""
    rows = (await conn.execute(text("""
        SELECT tc.table_name, kcu.column_name
        FROM information_schema.table_constraints tc
        JOIN information_schema.key_column_usage kcu
          ON tc.constraint_name = kcu.constraint_name AND tc.table_schema = kcu.table_schema
        JOIN information_schema.constraint_column_usage ccu
          ON tc.constraint_name = ccu.constraint_name AND tc.table_schema = ccu.table_schema
        WHERE tc.constraint_type = 'FOREIGN KEY' AND ccu.table_name = 'players'
    """))).all()
    out: dict[str, list[str]] = {}
    for table, column in rows:
        out.setdefault(table, []).append(column)
    return out


async def _table_columns(conn, table: str) -> list[str]:
    rows = (await conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t ORDER BY ordinal_position"
    ), {"t": table})).all()
    return [r[0] for r in rows]


def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


async def _fetch_rows(conn, table: str, where_sql: str, params: dict) -> tuple[list[str], list[dict]]:
    cols = await _table_columns(conn, table)
    col_list = ", ".join(_quote_ident(c) for c in cols)
    result = await conn.execute(
        text(f'SELECT {col_list} FROM {_quote_ident(table)} WHERE {where_sql}'), params
    )
    rows = [dict(zip(cols, r)) for r in result.all()]
    return cols, rows


async def _insert_rows(conn, table: str, cols: list[str], rows: list[dict]) -> int:
    if not rows:
        return 0
    col_list = ", ".join(_quote_ident(c) for c in cols)
    placeholders = ", ".join(f":{c}" for c in cols)
    await conn.execute(
        text(f'INSERT INTO {_quote_ident(table)} ({col_list}) VALUES ({placeholders})'),
        rows,
    )
    return len(rows)


async def _insert_rows_with_progress(
    session: AsyncSession, task_id: str, table: str, cols: list[str], rows: list[dict],
) -> int:
    """Same as _insert_rows, but in batches of _BATCH_SIZE with a live
    progress update after each — this is the one place true row-level
    "Processing X N of M" progress is possible, since we're writing the rows
    ourselves rather than going through pg_dump/pg_restore's opaque
    table-at-a-time streaming.

    Progress is written on a SEPARATE, short-lived session/connection, not
    ``session`` (which holds the table's restore transaction) — committing
    ``session`` mid-restore to report progress would turn "one transaction
    per table" into partial, uncommittable-as-a-whole batches, weakening the
    exact safety property this module's docstring promises."""
    total = len(rows)
    if not total:
        return 0
    inserted = 0
    for start in range(0, total, _BATCH_SIZE):
        batch = rows[start:start + _BATCH_SIZE]
        inserted += await _insert_rows(session, table, cols, batch)
        try:
            async with async_session_maker() as progress_session:
                await backup_progress.set_progress(
                    progress_session, task_id, stage=table, current=inserted, total=total,
                    message=f"Processing {table} {inserted} of {total}",
                )
        except Exception as e:  # progress reporting must never break the actual restore
            logger.warning("club_restore: progress update failed for %s: %s", table, e)
    return inserted


async def plan_and_run_club_restore(
    *,
    live_session: AsyncSession,
    scratch_dsn: str,
    org_id: str,
    task_id: str,
    snapshot_dir: str,
    apply: bool = False,
) -> dict:
    """Restores one org's data from the scratch DB (a bundle already
    `pg_restore`'d there — see ops/backup/restore.sh restore-club) into the
    live DB. With ``apply=False`` (the default) this only REPORTS what would
    happen — no write, no snapshot file, completely safe to run repeatedly.
    With ``apply=True`` it snapshots the club's current live rows to
    ``snapshot_dir/<task_id>.json`` first, then does the real delete+insert.

    Returns a summary dict: {tables: {name: {live_rows, scratch_rows,
    restored}}, player_ids_in_scope, snapshot_path}.
    """
    scratch_engine = create_async_engine(scratch_dsn)
    summary: dict = {"tables": {}, "apply": apply}
    snapshot: dict = {}

    async def _report(stage: str, current: int, total: int, message: str) -> None:
        try:
            async with async_session_maker() as progress_session:
                await backup_progress.set_progress(
                    progress_session, task_id, stage=stage, current=current, total=total, message=message,
                )
        except Exception as e:
            logger.warning("club_restore: progress update failed for %s: %s", stage, e)

    try:
        async with scratch_engine.connect() as scratch_conn:
            direct_tables = await _direct_org_tables(scratch_conn)
            game_tables = await _game_scoped_tables(scratch_conn)
            player_fks = await _player_fk_columns(scratch_conn)
            total_tables = len(direct_tables) + len(game_tables)
            table_idx = 0

            # The org's player ids AS OF THE BACKUP — player ids are
            # deterministic (uuid5(org, guid) or the raw guid, see the
            # per-club-player-id scheme in CLAUDE.md) so they match between
            # scratch and live for the SAME organisation.
            scratch_player_ids = [
                str(r[0]) for r in (await scratch_conn.execute(
                    text("SELECT id FROM players WHERE organisation_id = :org"), {"org": org_id}
                )).all()
            ]
            summary["player_ids_in_scope"] = len(scratch_player_ids)

            # --- Direct tables --------------------------------------------------
            for table in direct_tables:
                table_idx += 1
                await _report(table, table_idx, total_tables,
                              f"{'Analyzing' if not apply else 'Reading'} {table} ({table_idx}/{total_tables})...")
                try:
                    cols, scratch_rows = await _fetch_rows(
                        scratch_conn, table, "organisation_id = :org", {"org": org_id}
                    )
                except Exception as e:
                    logger.warning("club_restore: skipping direct table %s: %s", table, e)
                    continue
                live_count = (await live_session.execute(
                    text(f'SELECT COUNT(*) FROM {_quote_ident(table)} WHERE organisation_id = :org'),
                    {"org": org_id},
                )).scalar() or 0
                summary["tables"][table] = {
                    "kind": "direct", "live_rows": live_count, "scratch_rows": len(scratch_rows),
                }
                if apply:
                    snapshot[table] = {"kind": "direct", "rows": await _snapshot_live_rows(
                        live_session, table, "organisation_id = :org", {"org": org_id}
                    )}
                    await live_session.execute(
                        text(f'DELETE FROM {_quote_ident(table)} WHERE organisation_id = :org'),
                        {"org": org_id},
                    )
                    restored = await _insert_rows_with_progress(live_session, task_id, table, cols, scratch_rows)
                    await live_session.commit()
                    summary["tables"][table]["restored"] = restored
                    await backup_progress.mark_stage_done(live_session, task_id, table, restored)
                else:
                    await backup_progress.mark_stage_done(live_session, task_id, table, len(scratch_rows))

            # --- Game-scoped tables, scoped via player FK columns ---------------
            if scratch_player_ids:
                for table in game_tables:
                    table_idx += 1
                    fk_cols = player_fks.get(table)
                    if not fk_cols:
                        logger.info(
                            "club_restore: %s has no players.id FK — skipping (can't safely "
                            "attribute rows to an org; e.g. fee_match_days is member-scoped, "
                            "not player-scoped, and needs its own handling if ever added here)",
                            table,
                        )
                        continue
                    await _report(table, table_idx, total_tables,
                                  f"{'Analyzing' if not apply else 'Reading'} {table} ({table_idx}/{total_tables})...")
                    or_clause = " OR ".join(f'{_quote_ident(c)} = ANY(:pids)' for c in fk_cols)
                    try:
                        cols, scratch_rows = await _fetch_rows(
                            scratch_conn, table, or_clause, {"pids": scratch_player_ids}
                        )
                    except Exception as e:
                        logger.warning("club_restore: skipping game-scoped table %s: %s", table, e)
                        continue
                    live_count = (await live_session.execute(
                        text(f'SELECT COUNT(*) FROM {_quote_ident(table)} WHERE {or_clause}'),
                        {"pids": scratch_player_ids},
                    )).scalar() or 0
                    summary["tables"][table] = {
                        "kind": "game_scoped", "live_rows": live_count, "scratch_rows": len(scratch_rows),
                    }
                    if apply:
                        snapshot[table] = {
                            "kind": "game_scoped",
                            "fk_cols": fk_cols,
                            "rows": await _snapshot_live_rows(
                                live_session, table, or_clause, {"pids": scratch_player_ids}
                            ),
                        }
                        await live_session.execute(
                            text(f'DELETE FROM {_quote_ident(table)} WHERE {or_clause}'),
                            {"pids": scratch_player_ids},
                        )
                        restored = await _insert_rows_with_progress(live_session, task_id, table, cols, scratch_rows)
                        await live_session.commit()
                        summary["tables"][table]["restored"] = restored
                        await backup_progress.mark_stage_done(live_session, task_id, table, restored)
                    else:
                        await backup_progress.mark_stage_done(live_session, task_id, table, len(scratch_rows))
    finally:
        await scratch_engine.dispose()

    if apply:
        path = Path(snapshot_dir) / f"{task_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "org_id": org_id, "task_id": task_id,
            "player_ids": scratch_player_ids,
            "tables": snapshot,
        }, default=str))
        summary["snapshot_path"] = str(path)

    return summary


async def _snapshot_live_rows(live_session: AsyncSession, table: str, where_sql: str, params: dict) -> list[dict]:
    cols, rows = await _fetch_rows(live_session, table, where_sql, params)
    return rows


async def rollback_club_restore(*, live_session: AsyncSession, snapshot_path: str) -> dict:
    """Undo a previous ``apply=True`` restore: deletes whatever's there now
    for each snapshotted table's scope and re-inserts the pre-restore rows
    from the snapshot file. Same delete-then-insert-per-table transaction
    pattern as the restore itself."""
    data = json.loads(Path(snapshot_path).read_text())
    org_id = data["org_id"]
    player_ids = data.get("player_ids") or []
    restored_counts = {}
    for table, entry in data["tables"].items():
        rows = entry["rows"]
        if entry["kind"] == "direct":
            await live_session.execute(
                text(f'DELETE FROM {_quote_ident(table)} WHERE organisation_id = :org'), {"org": org_id}
            )
        else:
            fk_cols = entry.get("fk_cols") or []
            if not fk_cols or not player_ids:
                # Nothing to safely scope a delete by — only re-insert what we snapshotted.
                pass
            else:
                or_clause = " OR ".join(f'{_quote_ident(c)} = ANY(:pids)' for c in fk_cols)
                await live_session.execute(
                    text(f'DELETE FROM {_quote_ident(table)} WHERE {or_clause}'), {"pids": player_ids}
                )
        if rows:
            cols = list(rows[0].keys())
            await _insert_rows(live_session, table, cols, rows)
        await live_session.commit()
        restored_counts[table] = len(rows)
    return {"org_id": org_id, "tables_restored": restored_counts}
