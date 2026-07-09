"""Cache the last-computed Twenty engagementScore/-Tier onto marketing_clubs.

_engagement() (twenty_sync.py) previously only ever computed the score to PATCH
it out to Twenty CRM — nothing local ever stored it, so filtering the Club
Directory / BetterComms Contacts+Lists / Segments by engagement score meant
recomputing a per-club usage_events + email_events scan for every candidate row,
not viable at directory scale (~6500 clubs). Every _engagement() call now writes
engagement_score/.engagement_tier/.engagement_scored_at onto the club row itself,
regardless of which of the four call sites triggered it.

Revision ID: 134
Revises: 133
Create Date: 2026-07-09
"""
from alembic import op


revision = '134'
down_revision = '133'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_score INTEGER")
    op.execute("ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_tier TEXT")
    op.execute(
        "ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_scored_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_scored_at")
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_tier")
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_score")
