"""club_room_theme_shuffle — Club Room Mode gets a light/dark stage theme and
a shuffle-the-playlist option, plus three new slide types (leaderboard,
records, statlab_report) that need no schema change (they're just new
`slide_type` string values in the existing `club_room_slides.config` JSONB).

Revision ID: 207
Revises: 206
Create Date: 2026-08-02
"""
from alembic import op

revision = '207'
down_revision = '206'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS theme TEXT NOT NULL DEFAULT 'dark'"
    )
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS shuffle BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS shuffle")
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS theme")
