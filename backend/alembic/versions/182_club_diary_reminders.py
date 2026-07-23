"""Club Diary — optional reminder emails to the person responsible.

Opt-in per task definition (reminder_enabled, default false — most clubs
will just use the Board view with no emails at all), with a configurable
lead time (reminder_days_before). Throttled per-occurrence via
last_reminder_sent_at, same pattern as the qualification/fee reminders
built earlier this session.

Revision ID: 182
Revises: 181
Create Date: 2026-07-23
"""
from alembic import op

revision = '182'
down_revision = '181'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS reminder_enabled BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS reminder_days_before INTEGER NOT NULL DEFAULT 14"
    )
    op.execute(
        "ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS last_reminder_sent_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE club_diary_task_occurrences DROP COLUMN IF EXISTS last_reminder_sent_at")
    op.execute("ALTER TABLE club_diary_task_definitions DROP COLUMN IF EXISTS reminder_days_before")
    op.execute("ALTER TABLE club_diary_task_definitions DROP COLUMN IF EXISTS reminder_enabled")
