"""CRM deal Product Interest source (auto | manual)

Revision ID: 186
Revises: 185
Create Date: 2026-07-24
"""
from alembic import op

revision = '186'
down_revision = '185'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS product_interest_source "
        "TEXT NOT NULL DEFAULT 'auto'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS product_interest_source")
