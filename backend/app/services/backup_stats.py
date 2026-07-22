"""Database size/record-count stats for the Backups page and for the stats
snapshot stamped onto each ``backup_tasks`` row.

There's no per-tenant size in a shared Postgres schema, so per-club size is
an ESTIMATE: each org-scoped table's on-disk size (``pg_total_relation_size``)
is split across clubs in proportion to each club's share of that table's row
count. This is exact for row counts (a real ``COUNT(*) ... GROUP BY``) and a
reasonable approximation for bytes (assumes roughly uniform row size within a
table, which holds well enough for cricket scorecard data — a bowling_spells
row is much the same size whoever it belongs to).

Tables are discovered from ``information_schema`` rather than hardcoded, so a
newly added org-scoped table is picked up automatically:
  - "direct" tables have an ``organisation_id`` column.
  - "game-scoped" tables have a ``game_id`` column and are attributed via
    games -> grades -> seasons -> organisation_id (games has no
    organisation_id column of its own).
"""
from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def _direct_org_tables(db: AsyncSession) -> list[str]:
    rows = (await db.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'organisation_id'"
    ))).all()
    return [r[0] for r in rows]


async def _game_scoped_tables(db: AsyncSession) -> list[str]:
    rows = (await db.execute(text(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'game_id'"
    ))).all()
    return [r[0] for r in rows]


async def compute_db_stats(db: AsyncSession) -> dict:
    """Returns ``{db_size_bytes, uploads_size_bytes: None, total_row_count,
    club_stats: {org_id: {name, rows, size_bytes}}}``. ``uploads_size_bytes``
    is always None here — that's filesystem-side, stamped by the backup
    script itself, not computed from the DB."""
    db_size = (await db.execute(text("SELECT pg_database_size(current_database())"))).scalar() or 0

    orgs = (await db.execute(text("SELECT id, name FROM organisations"))).all()
    org_names = {str(r[0]): r[1] for r in orgs}
    club_rows: dict[str, int] = {str(r[0]): 0 for r in orgs}
    club_bytes: dict[str, float] = {str(r[0]): 0.0 for r in orgs}
    total_rows = 0

    direct_tables = await _direct_org_tables(db)
    for table in direct_tables:
        try:
            table_bytes = (await db.execute(
                text(f'SELECT pg_total_relation_size(\'"{table}"\')')
            )).scalar() or 0
            rows = (await db.execute(text(
                f'SELECT organisation_id, COUNT(*) FROM "{table}" '
                f'WHERE organisation_id IS NOT NULL GROUP BY organisation_id'
            ))).all()
        except Exception:
            continue  # a table can vanish/lock mid-scan; skip rather than fail the whole snapshot
        table_total_rows = sum(r[1] for r in rows)
        total_rows += table_total_rows
        if table_total_rows == 0:
            continue
        for org_id, count in rows:
            key = str(org_id)
            club_rows[key] = club_rows.get(key, 0) + count
            club_bytes[key] = club_bytes.get(key, 0.0) + table_bytes * (count / table_total_rows)

    game_tables = await _game_scoped_tables(db)
    for table in game_tables:
        if table == "games":
            continue
        try:
            table_bytes = (await db.execute(
                text(f'SELECT pg_total_relation_size(\'"{table}"\')')
            )).scalar() or 0
            rows = (await db.execute(text(
                f'SELECT s.organisation_id, COUNT(*) FROM "{table}" t '
                f'JOIN games g ON g.id = t.game_id '
                f'JOIN grades gr ON gr.id = g.grade_id '
                f'JOIN seasons s ON s.id = gr.season_id '
                f'GROUP BY s.organisation_id'
            ))).all()
        except Exception:
            continue
        table_total_rows = sum(r[1] for r in rows)
        total_rows += table_total_rows
        if table_total_rows == 0:
            continue
        for org_id, count in rows:
            key = str(org_id)
            club_rows[key] = club_rows.get(key, 0) + count
            club_bytes[key] = club_bytes.get(key, 0.0) + table_bytes * (count / table_total_rows)

    club_stats = {
        org_id: {
            "name": org_names.get(org_id, org_id),
            "rows": club_rows.get(org_id, 0),
            "size_bytes": int(club_bytes.get(org_id, 0.0)),
        }
        for org_id in org_names
    }

    return {
        "db_size_bytes": int(db_size),
        "total_row_count": total_rows,
        "club_stats": club_stats,
    }
