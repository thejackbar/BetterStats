"""BetterComms — distinguish manually-created lists from auto-generated ones

Adds ``comms_lists.source`` (``manual`` | ``auto``, default ``manual``) and
``comms_lists.origin`` (a short human label for what generated an auto list,
e.g. "CRM Sales Pipeline"). The Lists page splits into a "Your lists" section
(source=manual) and an "Auto-generated lists" section (source=auto) for super
admins. Auto lists are minted by other BetterCricket functions — the first is
the CRM Sales Pipeline "Create List" action.

Non-breaking: additive columns with a safe default, so every existing list
reads as a manual list.

Revision ID: 203
Revises: 202
Create Date: 2026-07-31
"""
from alembic import op


revision = "203"
down_revision = "202"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE comms_lists ADD COLUMN IF NOT EXISTS "
        "source TEXT NOT NULL DEFAULT 'manual'"
    )
    op.execute(
        "ALTER TABLE comms_lists ADD COLUMN IF NOT EXISTS origin TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE comms_lists DROP COLUMN IF EXISTS origin")
    op.execute("ALTER TABLE comms_lists DROP COLUMN IF EXISTS source")
