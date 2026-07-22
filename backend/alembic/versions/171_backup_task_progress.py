"""Backup/restore task live progress

Adds a `progress` JSONB column to `backup_tasks` so a running task can report
what it's up to — which table/entity it's currently on, current/total for a
progress bar, a human message ("Processing Player 176 of 876"), and a
running tally of finished stages ("Players: 876, Games: 3957, ..."). Updated
throughout a run by backup_task.py / club_restore.py, polled by the Super
Admin Backups page while a task is `running`.

Revision ID: 171
Revises: 170
Create Date: 2026-07-21
"""
from alembic import op


revision = '171'
down_revision = '170'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS progress JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE backup_tasks DROP COLUMN IF EXISTS progress")
