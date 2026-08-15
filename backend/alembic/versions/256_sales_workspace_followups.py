"""Sales Workspace — Phase 2a: Follow-ups queue + do-not-contact.

Two small additive pieces on top of migration 255:

- ``crm_activities.follow_up_done_at`` — a follow-up is "pending" while
  ``next_follow_up_at IS NOT NULL AND follow_up_done_at IS NULL``. Explicit
  resolution (a "Mark done" action) rather than inferring it from a later
  call, so a rep can note "I called back, we're square" without being forced
  to log a whole second call just to clear the queue.
- ``marketing_club_contacts.do_not_contact`` / ``.do_not_contact_reason`` —
  the PERSON-level "don't call me" signal (distinct from ``subscribed``,
  which is email-opt-out only). The CLUB-level equivalent deliberately
  reuses the existing ``marketing_clubs.not_interested`` flag (migration
  095) rather than a second column — it already short-circuits engagement
  scoring platform-wide (see twenty_sync._engagement's early return), which
  is exactly the right behaviour for "stop treating this club as a lead."

Revision ID: 256
Revises: 255
Create Date: 2026-08-15
"""
from alembic import op


revision = '256'
down_revision = '255'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS follow_up_done_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS do_not_contact "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS do_not_contact_reason TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE marketing_club_contacts DROP COLUMN IF EXISTS do_not_contact_reason")
    op.execute("ALTER TABLE marketing_club_contacts DROP COLUMN IF EXISTS do_not_contact")
    op.execute("ALTER TABLE crm_activities DROP COLUMN IF EXISTS follow_up_done_at")
