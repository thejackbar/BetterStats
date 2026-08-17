"""Comms templates gain a subject line.

``comms_templates`` (migration 113) has always been HTML-body-only — a
campaign supplies its own subject separately (``comms_campaigns.subject``).
The Sales Workspace's three built-in one-to-one emails ("Send information",
"Trial information", "Book a demo") were previously hardcoded Python
f-strings in ``services/sales_email.py``; they now live here as ordinary,
editable ``comms_templates`` rows (seeded into the platform's marketing
outreach org — ``organisations.is_marketing_outreach`` — so a super admin
edits them from the normal BetterAdmin -> Comms -> Templates screen, the
same screen and editor every other template already uses), and a template
row needs somewhere to hold its own subject line for that to work.

Nullable and additive only — every existing template (a club's own
BetterComms library) keeps working exactly as before; ``subject`` is simply
unused (None) for a template that's only ever attached to a campaign, which
supplies its own subject.

Revision ID: 260
Revises: 259
Create Date: 2026-08-19
"""
from alembic import op


revision = '260'
down_revision = '259'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE comms_templates ADD COLUMN IF NOT EXISTS subject TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_templates DROP COLUMN IF EXISTS subject")
