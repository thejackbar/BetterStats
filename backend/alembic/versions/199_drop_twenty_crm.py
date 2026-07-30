"""Drop the Twenty CRM integration's DB artifacts.

Twenty is decommissioned and replaced by the in-house BetterCricket CRM
(services/crm.py). The engagement scoring that fed Twenty was retained and
moved to services/crm_sync.py (it still populates marketing_clubs.engagement_*,
which the BetterCricket CRM reads), so those columns stay. What goes here:

  * ``twenty_links`` — the Twenty membership/id-mapping ledger. No BetterCricket
    code reads it any more.
  * ``club_request_events.twenty_task_id`` / ``.twenty_task_status`` — the
    best-effort Twenty-task push bookkeeping. The telemetry row itself
    (club_request_events) stays; only these two Twenty-only columns go.

Non-destructive to everything else, and safe to re-run (IF EXISTS everywhere).
Mirrored idempotently in app/main.py lifespan (these were `CREATE TABLE IF NOT
EXISTS` / column mirrors that have been removed there).
"""
from alembic import op

revision = "199"
down_revision = "198"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("DROP TABLE IF EXISTS twenty_links")
    op.execute("ALTER TABLE club_request_events DROP COLUMN IF EXISTS twenty_task_id")
    op.execute("ALTER TABLE club_request_events DROP COLUMN IF EXISTS twenty_task_status")


def downgrade():
    # Twenty is gone; recreate only the bare shapes so a downgrade doesn't error.
    op.execute("""
        CREATE TABLE IF NOT EXISTS twenty_links (
            entity_type TEXT NOT NULL,
            bc_id TEXT NOT NULL,
            twenty_id TEXT NOT NULL,
            content_hash TEXT,
            last_synced_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (entity_type, bc_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_twenty_links_twenty ON twenty_links(twenty_id)")
    op.execute("ALTER TABLE club_request_events ADD COLUMN IF NOT EXISTS twenty_task_id TEXT")
    op.execute("ALTER TABLE club_request_events ADD COLUMN IF NOT EXISTS twenty_task_status "
               "TEXT NOT NULL DEFAULT 'pending'")
