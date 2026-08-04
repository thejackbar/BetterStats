"""usage_events geo indexes — the two scans behind the connection-pool outage.

1. idx_usage_events_ip_hash_created. usage_tracker._enrich_geo backfills a
   freshly-geolocated IP's rows with `WHERE ip_hash = ...`, and ip_hash has
   never been indexed on this table (login_attempts indexes its own since day
   one; usage_events was missed). usage_events is append-only with no retention
   job, so that UPDATE was a full table scan per newly-seen IP, holding a
   connection and row locks for its whole duration. Enough of those at once and
   the SQLAlchemy pool is empty, which is what surfaced as
   `QueuePool limit of size 20 overflow 30 reached` on /club-admin/usage/geo —
   the timeout hit in get_current_user, before the handler ever ran.

2. idx_usage_events_geo_map. Covers that same endpoint's own read: anonymous,
   geo-enriched rows by recency. Partial on `lat IS NOT NULL AND user_id IS
   NULL`, so it only carries the rows the map can actually plot.

Mirrored idempotently in app/main.py lifespan (usage_events block).

DEPLOY NOTE: a plain CREATE INDEX takes a SHARE lock, blocking writes to
usage_events while it builds — on a large table that can be a minute or two of
dropped breadcrumbs (they fail silently by design). Run these by hand with
CREATE INDEX CONCURRENTLY first if that matters; CONCURRENTLY cannot be used
here because both alembic and the lifespan mirror run inside a transaction.

Revision ID: 214
Revises: 213
Create Date: 2026-08-04
"""
from alembic import op

revision = "214"
down_revision = "213"
branch_labels = None
depends_on = None

STATEMENTS = [
    "CREATE INDEX IF NOT EXISTS idx_usage_events_ip_hash_created "
    "ON usage_events(ip_hash, created_at DESC) WHERE ip_hash IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS idx_usage_events_geo_map "
    "ON usage_events(created_at DESC) WHERE lat IS NOT NULL AND user_id IS NULL",
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_usage_events_ip_hash_created")
    op.execute("DROP INDEX IF EXISTS idx_usage_events_geo_map")
