"""BetterCRM — optional pipeline templates ("trackers") for the club module.

Per direct instruction: sponsorship pursuit, grant applications and alumni
fundraising are not universal to every club, so the club-facing CRM's
pipelines become opt-in "trackers" a club adds from a small preset catalogue
(or builds fully custom) rather than one auto-seeded default "Sponsors"
pipeline (which is what migration 173 originally shipped). Adds
``crm_pipelines.template_key`` (which preset, if any — NULL for a custom
tracker) and ``.is_active`` (a club "removing" a tracker deactivates it,
keeping its historical deals, rather than deleting them).

Revision ID: 174
Revises: 173
Create Date: 2026-07-23
"""
from alembic import op


revision = '174'
down_revision = '173'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS template_key TEXT")
    op.execute("ALTER TABLE crm_pipelines ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT true")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_pipelines_template ON crm_pipelines(organisation_id, template_key)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_crm_pipelines_template")
    op.execute("ALTER TABLE crm_pipelines DROP COLUMN IF EXISTS is_active")
    op.execute("ALTER TABLE crm_pipelines DROP COLUMN IF EXISTS template_key")
