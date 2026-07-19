"""Meta Ads dashboard — scope snapshots and lead adjustments to a campaign

Neither `meta_ad_snapshots` nor `meta_lead_adjustments` recorded which real
Meta campaign a row belonged to — the tables were built assuming there would
only ever be one campaign in flight (whatever `settings.meta_campaign_id`
pointed at). That assumption broke the moment the dashboard was repointed
from the finished July campaign (BC_AU_Traffic_ClubHistory_Jul2026,
120249237210710121) to the new self-serve one
(BC_AU_SelfServe_Aug2026, 120249890918010121):

- `meta_ad_snapshots`' unique key was (snapshot_date, level, ad_id) with no
  campaign — the campaign-level row for "today" would silently belong to
  whichever campaign happened to run the snapshot job last, and
  `get_history`'s 14-day trend query had NO campaign filter at all, so the
  chart stitched the old campaign's daily performance directly into the
  new one's with no seam visible.
- `meta_lead_adjustments` (the manual +/- reconciliation log) had no
  campaign column whatsoever — any correction made during the July
  campaign would silently keep inflating/deflating the new campaign's
  "Meta-attributed conversions" number forever.

Adds `campaign_id TEXT` to both tables, backfills every existing row with
the July campaign's id (the only campaign that existed while they were
written), and rebuilds the snapshot table's unique index to include it —
so a campaign switch on the same calendar day can't collide with an
already-written row either. `services/meta_ads.py`'s read/write paths are
updated in the same change to filter by `settings.meta_campaign_id`.

Revision ID: 162
Revises: 161
Create Date: 2026-07-19
"""
from alembic import op


revision = '162'
down_revision = '161'
branch_labels = None
depends_on = None

# The only campaign id that existed while every pre-existing row in these
# tables was written — see settings.meta_campaign_id's old default.
_LEGACY_CAMPAIGN_ID = '120249237210710121'


def upgrade() -> None:
    op.execute("ALTER TABLE meta_ad_snapshots ADD COLUMN IF NOT EXISTS campaign_id TEXT")
    op.execute(f"UPDATE meta_ad_snapshots SET campaign_id = '{_LEGACY_CAMPAIGN_ID}' WHERE campaign_id IS NULL")
    op.execute("DROP INDEX IF EXISTS uq_meta_ad_snapshots_date_level_ad")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad_campaign "
        "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''), COALESCE(campaign_id, ''))"
    )

    op.execute("ALTER TABLE meta_lead_adjustments ADD COLUMN IF NOT EXISTS campaign_id TEXT")
    op.execute(f"UPDATE meta_lead_adjustments SET campaign_id = '{_LEGACY_CAMPAIGN_ID}' WHERE campaign_id IS NULL")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_meta_ad_snapshots_date_level_ad_campaign")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_meta_ad_snapshots_date_level_ad "
        "ON meta_ad_snapshots(snapshot_date, level, COALESCE(ad_id, ''))"
    )
    op.execute("ALTER TABLE meta_ad_snapshots DROP COLUMN IF EXISTS campaign_id")
    op.execute("ALTER TABLE meta_lead_adjustments DROP COLUMN IF EXISTS campaign_id")
