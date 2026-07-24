"""CRM pipeline removed_stage_keys — stops a deliberately-deleted default
stage (e.g. Self-Serve Trial) from being silently auto-recreated by the
platform-pipeline reconciliation on the very next read.

Revision ID: 188
Revises: 187
Create Date: 2026-07-24
"""
from alembic import op

revision = '188'
down_revision = '187'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS removed_stage_keys "
        "JSONB NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crm_pipelines DROP COLUMN IF EXISTS removed_stage_keys")
