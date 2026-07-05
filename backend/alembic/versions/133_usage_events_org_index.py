"""Index usage_events(org_id, created_at) for the engagement-score org_id scan.

twenty_sync._engagement scans usage_events filtered by org_id::text (a customer/
trial club's authenticated in-app activity) alongside the already-indexed utm_id
path (a prospect's anonymous marketing visits). org_id had no index at all, so
that branch was an unindexed scan on every refresh_engagement / export_to_twenty
call — cheap on a small table, real cost once it grows. Partial (only rows that
carry an org_id — anonymous marketing rows never do) so it stays small.

Revision ID: 133
Revises: 132
Create Date: 2026-07-05
"""
from alembic import op


revision = '133'
down_revision = '132'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_org_created "
        "ON usage_events(org_id, created_at DESC) WHERE org_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_usage_events_org_created")
