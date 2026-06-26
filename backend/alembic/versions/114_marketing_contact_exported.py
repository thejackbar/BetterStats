"""Marketing club directory — per-contact exported flag

``marketing_club_contacts.exported_at`` records when a contact was pushed into
BetterComms (``comms_contacts`` under the outreach org). It lets the directory
show an "exported" badge, lets the export filters hide contacts already in
BetterComms (so a re-export never duplicates), and is cleared again when the
matching BetterComms contact is deleted or reconciled by Sync suppressions.

Mirrored idempotently in main.py lifespan.

Revision ID: 114
Revises: 113
Create Date: 2026-06-26
"""
from alembic import op


revision = '114'
down_revision = '113'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE marketing_club_contacts ADD COLUMN IF NOT EXISTS exported_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE marketing_club_contacts DROP COLUMN IF EXISTS exported_at")
