"""BetterComms — per-contact merge-variable overrides

``comms_contacts.merge_vars`` is a JSONB map of editable merge-variable keys
(first_name / club / association / utm_code / state / website) to a per-contact
value. An override wins over the value derived from the linked Clubs Directory
club or the sending org, so any contact — manually added, imported, or exported
from the directory — can have every merge variable filled in and edited.

Mirrored idempotently in main.py lifespan.

Revision ID: 115
Revises: 114
Create Date: 2026-06-26
"""
from alembic import op


revision = '115'
down_revision = '114'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS merge_vars JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS merge_vars")
