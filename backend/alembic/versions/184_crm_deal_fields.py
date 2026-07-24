"""CRM deal onboarding method, lead source, discretionary discount fields

Revision ID: 184
Revises: 183
Create Date: 2026-07-24
"""
from alembic import op

revision = '184'
down_revision = '183'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS onboarding_method TEXT")
    op.execute("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS lead_source TEXT")
    op.execute("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_amount_cents INTEGER")
    op.execute("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_percent INTEGER")
    op.execute("ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS discount_reason TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS onboarding_method")
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS lead_source")
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS discount_amount_cents")
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS discount_percent")
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS discount_reason")
