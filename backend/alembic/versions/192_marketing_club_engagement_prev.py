"""marketing_clubs.engagement_score_prev / .engagement_score_prev_date — a
day-over-day baseline for the engagement score, so the CRM Sales Pipeline can
show a green up-arrow / red down-arrow on a deal card when its club's score
rose or fell from the previous calendar day. There is no engagement-score
history table; every _engagement() write (twenty_sync._apply_engagement_cache)
rolls the current value into _prev the first time it writes on a new calendar
day, so _prev always holds the last score recorded on an earlier day.

Revision ID: 192
Revises: 191
Create Date: 2026-07-29
"""
from alembic import op

revision = '192'
down_revision = '191'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score_prev INTEGER"
    )
    op.execute(
        "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score_prev_date DATE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_score_prev")
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_score_prev_date")
