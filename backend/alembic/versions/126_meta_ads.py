"""Meta Ads dashboard — daily campaign/ad snapshots

Adds ``meta_ad_snapshots`` — one row per day per level (campaign or ad), written
by the daily 09:00 Australia/Perth scheduled job (and by the on-demand Refresh
action) from the Meta Marketing API. Platform-level (not club-scoped) — this is
BetterCricket's own ad spend, not a club's data — so gated to super admins,
same posture as ``login_attempts`` / the marketing club directory.

Upserted on (snapshot_date, level, ad_id) so a same-day re-run (Refresh now, or
a re-fired 9am job) overwrites rather than duplicates.

Mirrored idempotently in main.py lifespan so the API boots even if alembic
hasn't run yet.

Revision ID: 126
Revises: 125
Create Date: 2026-07-03
"""
from alembic import op


revision = '126'
down_revision = '125'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS meta_ad_snapshots (
            id BIGSERIAL PRIMARY KEY,
            snapshot_date DATE NOT NULL,
            level TEXT NOT NULL,
            ad_id TEXT,
            ad_name TEXT,
            spend NUMERIC NOT NULL DEFAULT 0,
            impressions NUMERIC NOT NULL DEFAULT 0,
            link_clicks NUMERIC NOT NULL DEFAULT 0,
            link_ctr NUMERIC NOT NULL DEFAULT 0,
            landing_page_views NUMERIC NOT NULL DEFAULT 0,
            cost_per_lpv NUMERIC,
            leads NUMERIC NOT NULL DEFAULT 0,
            recommendation TEXT,
            recommendation_status TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad "
        "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''))"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meta_ad_snapshots_date "
        "ON meta_ad_snapshots(snapshot_date DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meta_ad_snapshots")
