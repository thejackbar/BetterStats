"""BetterComms sending tiers + club-request telemetry

Adds the per-club send tier (sandbox → production → suspended) and its optional
daily-cap override, the super-admin tier-increase request queue, and the generic
club→BetterCricket request telemetry table (which drives the automated Twenty
CRM task). Idempotent raw SQL — mirrored in main.py lifespan.

Revision ID: 125
Revises: 124
"""
from alembic import op

revision = "125"
down_revision = "124"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── per-club sending tier on organisations ──────────────────────────────
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
               "comms_tier TEXT NOT NULL DEFAULT 'sandbox'")
    # Per-club overrides of the global sandbox / production daily caps (NULL =
    # use the settings default), set when onboarding a club on BetterAdmin.
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
               "comms_sandbox_cap INTEGER")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
               "comms_production_cap INTEGER")
    # Existing clubs have already been sending as trusted tenants — start them in
    # 'production' so the new sandbox cap doesn't throttle live clubs on deploy.
    # New clubs created after this migration default to 'sandbox'.
    op.execute("UPDATE organisations SET comms_tier = 'production' "
               "WHERE comms_tier = 'sandbox'")

    # ── super-admin tier-increase request queue ─────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS comms_limit_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            current_tier TEXT,
            requested_tier TEXT NOT NULL DEFAULT 'production',
            requested_cap INTEGER,
            reason TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            decided_by UUID REFERENCES users(id) ON DELETE SET NULL,
            decided_at TIMESTAMPTZ,
            decision_note TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_comms_limit_requests_org "
               "ON comms_limit_requests(organisation_id)")
    # At most one open request per club (a partial unique index on pending rows).
    op.execute("CREATE UNIQUE INDEX IF NOT EXISTS uq_comms_limit_request_open "
               "ON comms_limit_requests(organisation_id) WHERE status = 'pending'")

    # ── generic club→BetterCricket request telemetry (feeds Twenty CRM) ──────
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_request_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            request_type TEXT NOT NULL,
            summary TEXT,
            detail JSONB,
            source TEXT NOT NULL DEFAULT 'app',
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            ref_table TEXT,
            ref_id UUID,
            twenty_task_id TEXT,
            twenty_task_status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_request_events_org "
               "ON club_request_events(organisation_id, created_at DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_request_events_type "
               "ON club_request_events(request_type, created_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS club_request_events")
    op.execute("DROP TABLE IF EXISTS comms_limit_requests")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS comms_production_cap")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS comms_sandbox_cap")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS comms_tier")
