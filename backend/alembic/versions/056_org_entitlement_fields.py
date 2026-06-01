"""org entitlement fields: tier + module_overrides

Better pivot · Phase 1. Adds the subscription tier (good/better/best) and an
à-la-carte module-override list to organisations — the foundation for module
gating (see app/auth/modules.py).

Existing clubs are backfilled to 'best' so the live pilot club keeps the
Select / Socials / Fees modules it is already using; new clubs default to 'good'
(Core / BetterStats only).

Revision ID: 056
Revises: 055
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '056'
down_revision = '055'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'organisations',
        sa.Column('tier', sa.Text(), nullable=False, server_default='good'),
    )
    op.add_column(
        'organisations',
        sa.Column(
            'module_overrides',
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    # Clubs that predate tiering keep full access — don't lock the live pilot
    # out of modules it already uses. New clubs created after this migration
    # take the column default ('good').
    op.execute("UPDATE organisations SET tier = 'best'")


def downgrade() -> None:
    op.drop_column('organisations', 'module_overrides')
    op.drop_column('organisations', 'tier')
