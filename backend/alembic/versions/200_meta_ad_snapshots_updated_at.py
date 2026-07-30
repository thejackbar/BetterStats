"""Meta Ads dashboard — a real "last updated" per snapshot row

`meta_ad_snapshots.created_at` is set once on INSERT and, because
`upsert_snapshot`'s `ON CONFLICT DO UPDATE` never touched it, stayed frozen
at whatever time the FIRST snapshot of that (date, level, ad, campaign)
landed. Every later same-day refresh (the daily job, a manual "Refresh now")
updated the row's numbers but not its timestamp, so the HQ dashboard's
"Last updated" label (`get_latest_summary` read `campaign_row.created_at`)
went stale after the first refresh of the day and didn't move again until
the next day's first snapshot.

Adds `updated_at`, backfilled from `created_at` for existing rows.
`services/meta_ads.py::upsert_snapshot` now sets it explicitly on both the
INSERT and the `DO UPDATE` branch, and `get_latest_summary` reads it back
instead of `created_at`.

Revision ID: 200
Revises: 199
Create Date: 2026-07-30
"""
from alembic import op


revision = "200"
down_revision = "199"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ")
    op.execute("UPDATE meta_ad_snapshots SET updated_at = created_at WHERE updated_at IS NULL")
    op.execute("ALTER TABLE meta_ad_snapshots ALTER COLUMN updated_at SET DEFAULT NOW()")
    op.execute("ALTER TABLE meta_ad_snapshots ALTER COLUMN updated_at SET NOT NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE meta_ad_snapshots DROP COLUMN IF EXISTS updated_at")
