"""BetterComms campaign name + description

Adds a human name and an optional description to a campaign (the "Email"), so
the Emails list reads by a chosen name rather than the subject line, with a
description underneath. A blank name is auto-filled from the subject + a
timestamp at send time (in the app), so this only needs the columns.

Revision ID: 132
Revises: 131
"""
from alembic import op

revision = "132"
down_revision = "131"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS name TEXT")
    op.execute("ALTER TABLE comms_campaigns ADD COLUMN IF NOT EXISTS description TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_campaigns DROP COLUMN IF EXISTS description")
    op.execute("ALTER TABLE comms_campaigns DROP COLUMN IF EXISTS name")
