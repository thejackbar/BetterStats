"""Add venue to games and catches_wk to fielding_stats

Revision ID: 026
Revises: 025
Create Date: 2026-05-23
"""
from alembic import op

revision = '026'
down_revision = '025'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS venue VARCHAR")
    op.execute("ALTER TABLE fielding_stats ADD COLUMN IF NOT EXISTS catches_wk INTEGER NOT NULL DEFAULT 0")


def downgrade() -> None:
    op.execute("ALTER TABLE fielding_stats DROP COLUMN IF EXISTS catches_wk")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS venue")
