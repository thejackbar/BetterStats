"""Backup/restore task tracking

The backup system (host-level pg_dump + uploads-volume script, run daily via
a systemd timer, or triggered on demand by a super admin) needs somewhere to
record what it did: one row per backup or restore attempt, so Super Admin can
see a history of requested/running/completed/failed runs plus the size and
row-count stats captured at the time.

This table is written by ``app/scripts/backup_task.py`` (invoked from the
host script via ``docker compose exec betterstats-backend python -m
app.scripts.backup_task ...``), and read by ``routers/backup_admin.py`` for
the Super Admin "Backups" page. It has no FK to a specific per-game table —
just an optional ``scope_org_id`` for a club-level restore task.

Revision ID: 166
Revises: 165
Create Date: 2026-07-21
"""
from alembic import op


revision = '166'
down_revision = '165'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS backup_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            task_type TEXT NOT NULL,                 -- backup | restore_full | restore_club
            status TEXT NOT NULL DEFAULT 'requested', -- requested | running | completed | failed
            scope_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
            triggered_by TEXT NOT NULL DEFAULT 'scheduled', -- scheduled | manual
            triggered_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            bundle_path TEXT,
            bundle_timestamp TIMESTAMPTZ,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at TIMESTAMPTZ,
            db_size_bytes BIGINT,
            uploads_size_bytes BIGINT,
            total_row_count BIGINT,
            club_stats JSONB,      -- {org_id: {"name": ..., "rows": N, "size_bytes": N}}
            error_message TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_backup_tasks_created ON backup_tasks(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_backup_tasks_status ON backup_tasks(status)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS backup_tasks")
