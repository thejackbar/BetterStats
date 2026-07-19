"""Setup Wizard analytics: first_opened_at on onboarding_wizard_state.

The wizard-analytics dashboard (routers/wizard_analytics.py) needs a real
"did this club ever look at the Setup Wizard" signal. The row's own
existence doesn't mean that — AdminLayout's /state poll (every admin page
mount, to show/hide the SETUP GUIDE button and sidebar badge) creates the
row too, for clubs that never opened the wizard page itself. first_opened_at
is stamped once, the first time POST /opened fires (i.e. the wizard page
actually mounted).

Revision ID: 163
Revises: 162
Create Date: 2026-07-19
"""
from alembic import op


revision = '163'
down_revision = '162'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute(
        "ALTER TABLE onboarding_wizard_state "
        "ADD COLUMN IF NOT EXISTS first_opened_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE onboarding_wizard_state DROP COLUMN IF EXISTS first_opened_at")
