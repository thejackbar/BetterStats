"""BetterStats (Core) as a managed module — backfill a core subscription per club

Core becomes a first-class managed module: a super admin can trial/activate it with
dates like any other, it's surfaced in Twenty, and its lifecycle controls whether the
public club surfaces render (see auth/modules.org_core_live + the public routers).

Backfill an active 'core' subscription row for every existing club, inheriting the
club's current org-wide status + renewal (paused/cancelled clubs get an active core
row — the org-level master switch already gates those, and we don't want to dark a
club purely from this migration). module_overrides is NOT touched (Core is the base,
not an add-on). Non-breaking: org_core_live fails open for any club still without a
core row.

Mirrored idempotently in main.py lifespan.

Revision ID: 122
Revises: 121
Create Date: 2026-06-30
"""
from alembic import op


revision = '122'
down_revision = '121'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO org_module_subscriptions
            (organisation_id, module_key, status, renewal_date, started_at, created_at, updated_at)
        SELECT
            o.id, 'core',
            CASE WHEN o.subscription_status IN ('active','trial','past_due')
                 THEN o.subscription_status ELSE 'active' END,
            o.renewal_date, NOW(), NOW(), NOW()
        FROM organisations o
        ON CONFLICT (organisation_id, module_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DELETE FROM org_module_subscriptions WHERE module_key = 'core'")
