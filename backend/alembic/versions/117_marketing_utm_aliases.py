"""Marketing UTM → club aliases (manual visit attribution)

The Clubs Directory marks a prospect club as "visited" when a public page_view
carries the club's UTM code. A campaign's utm_source isn't always the club's
utm_code though (e.g. utm_source='executive' was Leederville, and 'meta' /
'chatgpt.com' are ad/referrer noise), so an operator maps a raw UTM value to a
club here. A row with marketing_club_id NULL means the value is explicitly
ignored (not a club), so it drops off the "needs matching" list.

Revision ID: 117
Revises: 116
Create Date: 2026-06-28
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '117'
down_revision = '116'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'marketing_utm_aliases',
        sa.Column('id', UUID(as_uuid=True),
                  server_default=sa.text('gen_random_uuid()'), primary_key=True),
        sa.Column('utm_value', sa.Text(), nullable=False),
        sa.Column('marketing_club_id', UUID(as_uuid=True),
                  sa.ForeignKey('marketing_clubs.id', ondelete='CASCADE'), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
                  server_default=sa.text('NOW()'), nullable=False),
        sa.UniqueConstraint('utm_value', name='uq_marketing_utm_aliases_value'),
    )
    op.create_index('idx_marketing_utm_alias_club', 'marketing_utm_aliases',
                    ['marketing_club_id'])
    # Speeds the visit→club resolution (per-page_view utm_code lookups).
    op.create_index('idx_marketing_clubs_utm_code', 'marketing_clubs', ['utm_code'],
                    if_not_exists=True)


def downgrade() -> None:
    op.drop_index('idx_marketing_clubs_utm_code', table_name='marketing_clubs',
                  if_exists=True)
    op.drop_index('idx_marketing_utm_alias_club', table_name='marketing_utm_aliases')
    op.drop_table('marketing_utm_aliases')
