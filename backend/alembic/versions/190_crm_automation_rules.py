"""crm_automation_rules — configurable, persistent criteria for the platform
pipeline's automatic deal creation/stage-promotion, replacing the previously
hardcoded thresholds/target stages (Contact-Us enquiry count, engagement
score, trial requested/started, subscription won/cancelled, self-serve
signup). Managed by a super admin at /admin/super/crm-automation.

Revision ID: 190
Revises: 189
Create Date: 2026-07-27
"""
from alembic import op

revision = '190'
down_revision = '189'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_automation_rules (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            trigger TEXT NOT NULL,
            label TEXT NOT NULL,
            params JSONB NOT NULL DEFAULT '{}',
            target_stage_key TEXT NOT NULL,
            force BOOLEAN NOT NULL DEFAULT FALSE,
            enabled BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_automation_rules_trigger "
        "ON crm_automation_rules(trigger)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crm_automation_rules")
