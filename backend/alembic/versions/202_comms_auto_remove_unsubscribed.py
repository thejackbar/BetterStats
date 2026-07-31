"""BetterComms — auto-remove unsubscribed/bounced contacts from all lists

Adds ``organisations.comms_auto_remove_unsubscribed`` (default true). When on,
a contact that unsubscribes (one-click link) or is hard-bounced / marks spam is
automatically dropped from every static list it belongs to
(``comms_list_members``). See services/comms_lists.py and the Settings toggle in
routers/comms.py / CommsSettings.jsx.

Non-breaking: additive column with a safe default, so existing clubs keep the
tidy behaviour on by default and nothing is removed retroactively by the
migration itself.

Revision ID: 202
Revises: 201
Create Date: 2026-07-31
"""
from alembic import op


revision = "202"
down_revision = "201"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "comms_auto_remove_unsubscribed BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE organisations DROP COLUMN IF EXISTS comms_auto_remove_unsubscribed"
    )
