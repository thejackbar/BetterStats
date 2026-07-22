"""Meta Ads dashboard — track each ad's real Meta delivery status

`meta_ads.fetch_per_ad()` only ever pulled insights metrics (spend, clicks,
actions) from the Graph API — never the ad's own status — so the HQ
dashboard's per-ad badge (Winner/Laggard/On track) was purely
performance-derived and had no way to reflect an ad actually being paused
from Ads Manager (or via the Meta Ads MCP). A paused ad kept showing
whatever performance badge it last earned, which reads as live when it
isn't.

Adds `delivery_status` (Meta's `effective_status` string — ACTIVE, PAUSED,
ADSET_PAUSED, CAMPAIGN_PAUSED, ARCHIVED, DELETED, etc.) to
`meta_ad_snapshots`, ad-level rows only. `services/meta_ads.py`'s
`fetch_per_ad()`/`upsert_snapshot()`/`get_latest_summary()` are updated in
the same change to fetch, store, and read it back, and `ad_status()` now
reports a dedicated "paused" status whenever `delivery_status != 'ACTIVE'`,
ahead of the winner/laggard/on_track performance logic.

Revision ID: 172
Revises: 171
Create Date: 2026-07-22
"""
from alembic import op


revision = '172'
down_revision = '171'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS delivery_status TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE meta_ad_snapshots DROP COLUMN IF EXISTS delivery_status")
