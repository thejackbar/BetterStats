"""crm_deals.stage_auto_locked — once a human deliberately moves a deal's
stage, the auto-promotion engine (Contact-Us count, engagement score) stops
nudging that deal forward, so a manually-parked deal isn't silently re-moved
on the next automatic trigger.

Revision ID: 189
Revises: 188
Create Date: 2026-07-25
"""
from alembic import op

revision = '189'
down_revision = '188'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS stage_auto_locked "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crm_deals DROP COLUMN IF EXISTS stage_auto_locked")
