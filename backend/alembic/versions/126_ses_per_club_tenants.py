"""SES per-club tenants (multi-tenancy)

Adds the per-club Amazon SES tenant fields to organisations, so each club's
sending is isolated to its own tenant (reputation + pause). Populated by the
tenant provisioner (services/ses_tenants). Idempotent raw SQL, mirrored in the
main.py lifespan.

Revision ID: 126
Revises: 125
"""
from alembic import op

revision = "126"
down_revision = "125"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_name TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_id TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS ses_tenant_provisioned_at TIMESTAMPTZ")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
               "ses_tenant_paused BOOLEAN NOT NULL DEFAULT false")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS ses_tenant_paused")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS ses_tenant_provisioned_at")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS ses_tenant_id")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS ses_tenant_name")
