"""BetterComms — campaign remembers its template

``comms_campaigns.template_id`` records which template an email was started from,
so the compose screen can show it selected (and only warn when the user actually
switches to a different template). Copy-on-use still applies — the body is a copy
— this is just the origin link. FK SET NULL so deleting a template doesn't delete
the campaign.

Revision ID: 116
Revises: 115
Create Date: 2026-06-27
"""
from alembic import op


revision = '116'
down_revision = '115'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS template_id UUID "
               "REFERENCES comms_templates(id) ON DELETE SET NULL")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_campaigns DROP COLUMN IF EXISTS template_id")
