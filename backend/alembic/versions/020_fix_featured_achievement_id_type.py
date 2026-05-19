"""Fix achievement_id column type from UUID to INTEGER in yearbook_featured_achievements

Revision ID: 020
Revises: 019
Create Date: 2026-05-19
"""
from alembic import op

revision = '020'
down_revision = '019'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS yearbook_featured_achievements")
    op.execute("""
        CREATE TABLE yearbook_featured_achievements (
            id SERIAL PRIMARY KEY,
            yearbook_id UUID NOT NULL REFERENCES yearbooks(id) ON DELETE CASCADE,
            achievement_id INTEGER NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            CONSTRAINT uq_yb_featured_achievement UNIQUE (yearbook_id, achievement_id)
        )
    """)
    op.execute("""
        CREATE INDEX ix_yb_featured_yearbook
        ON yearbook_featured_achievements (yearbook_id)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS yearbook_featured_achievements")
