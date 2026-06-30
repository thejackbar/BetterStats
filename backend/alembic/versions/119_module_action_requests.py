"""Module action requests — the super-admin trial/subscription queue

A club admin (or a Twenty-origin event) raises a request to trial / subscribe to /
cancel a module. The request never changes entitlement itself — a super admin
actions it from the queue (start_module_trial etc.). Mirrors the
club_onboarding_requests pattern: lifecycle (outstanding -> completed / dismissed),
``source`` (app / super_admin / twenty), and audit timestamps.

``external_ref`` (+ a partial unique index) dedupes a Twenty-origin request.

Mirrored idempotently in main.py lifespan.

Revision ID: 119
Revises: 118
Create Date: 2026-06-30
"""
from alembic import op


revision = '119'
down_revision = '118'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS module_action_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            module_key TEXT NOT NULL,
            kind TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'outstanding',
            source TEXT NOT NULL DEFAULT 'app',
            note TEXT,
            requested_by UUID REFERENCES users(id) ON DELETE SET NULL,
            requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_by UUID REFERENCES users(id) ON DELETE SET NULL,
            completed_at TIMESTAMPTZ,
            result_subscription_id UUID REFERENCES org_module_subscriptions(id) ON DELETE SET NULL,
            external_ref TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_module_action_requests_status "
        "ON module_action_requests(status, requested_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_module_action_requests_org "
        "ON module_action_requests(organisation_id)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_module_action_external_ref "
        "ON module_action_requests(external_ref) WHERE external_ref IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS module_action_requests")
