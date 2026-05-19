"""Add yearbook_featured_achievements for pinning pulled awards to overview

Revision ID: 019
Revises: 018
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS yearbook_featured_achievements (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
            achievement_id UUID NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_yb_featured_achievement UNIQUE (yearbook_id, achievement_id)
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_yb_featured_yearbook
        ON yearbook_featured_achievements (yearbook_id)
    """)


def downgrade() -> None:
    op.drop_table('yearbook_featured_achievements')
