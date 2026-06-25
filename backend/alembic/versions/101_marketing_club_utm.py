"""Marketing club directory — per-club UTM code

Each club gets an editable UTM code for outreach links, defaulted to the first
word of the club name + "-cricket-club" (e.g. "Applecross Cricket Club" →
"applecross-cricket-club"). Stored so it can be hand-edited (multi-word clubs,
disambiguation) without the default clobbering the edit on a re-crawl.

Revision ID: 101
Revises: 100
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


revision = '101'
down_revision = '100'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('marketing_clubs', sa.Column('utm_code', sa.Text(), nullable=True))
    # Backfill existing rows: first word of the name (alphanumeric, lowercased) +
    # "-cricket-club".
    op.execute(r"""
        UPDATE marketing_clubs
        SET utm_code = lower(regexp_replace(split_part(name, ' ', 1), '[^a-zA-Z0-9]', '', 'g'))
                       || '-cricket-club'
        WHERE utm_code IS NULL
          AND coalesce(regexp_replace(split_part(name, ' ', 1), '[^a-zA-Z0-9]', '', 'g'), '') <> ''
    """)


def downgrade() -> None:
    op.drop_column('marketing_clubs', 'utm_code')
