"""org subscription fields: status + renewal_date + billing_cycle

Better pivot · Phase 3. Adds the manual-invoicing/subscription state to
organisations. `subscription_status` drives entitlement now (paused/cancelled
clubs fall back to Core only — see app/auth/modules.py); renewal_date and
billing_cycle reflect the manual-invoicing state in-app ahead of Stripe.

Existing clubs default to 'active' so nothing is locked out.

Revision ID: 057
Revises: 056
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa


revision = '057'
down_revision = '056'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'organisations',
        sa.Column('subscription_status', sa.Text(), nullable=False, server_default='active'),
    )
    op.add_column('organisations', sa.Column('renewal_date', sa.Date(), nullable=True))
    op.add_column('organisations', sa.Column('billing_cycle', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('organisations', 'billing_cycle')
    op.drop_column('organisations', 'renewal_date')
    op.drop_column('organisations', 'subscription_status')
