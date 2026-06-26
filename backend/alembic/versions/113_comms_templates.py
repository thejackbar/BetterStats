"""BetterComms Phase 3 — email templates + campaign UTM

``comms_templates`` stores reusable email HTML (built from scratch, pasted, or
imported from a .html file). A campaign can start from a template. Rendering
merges variables anywhere (including inside link URLs), auto-appends the
campaign's UTM tags to outbound links, and always injects the mandatory
unsubscribe footer. ``comms_campaigns.utm`` holds the per-campaign UTM tags
(source / medium / campaign / content / term). See
docs/bettercomms-architecture.md.

Mirrored idempotently in main.py lifespan.

Revision ID: 113
Revises: 112
Create Date: 2026-06-26
"""
from alembic import op


revision = '113'
down_revision = '112'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS comms_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            html TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comms_template_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_comms_templates_org ON comms_templates(organisation_id)")
    op.execute("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS utm JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_campaigns DROP COLUMN IF EXISTS utm")
    op.execute("DROP TABLE IF EXISTS comms_templates")
