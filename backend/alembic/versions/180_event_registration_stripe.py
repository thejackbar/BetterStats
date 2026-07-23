"""Event registration Stripe Connect payment fields.

Wires the SAME per-club Stripe Connect account (member portal fee payments,
merch storefront) into Events/Ticketing checkout — a priced event
registration created while the club's connected account has
charges_enabled now gets a real Checkout Session instead of always landing
`awaiting_payment` for manual reconciliation. A club that hasn't connected
Stripe yet keeps the existing manual-reconciliation behaviour unchanged.

Revision ID: 180
Revises: 179
Create Date: 2026-07-23
"""
from alembic import op

revision = '180'
down_revision = '179'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE event_registrations ADD COLUMN IF NOT EXISTS stripe_checkout_session_id TEXT")
    op.execute("ALTER TABLE event_registrations ADD COLUMN IF NOT EXISTS stripe_payment_intent_id TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE event_registrations DROP COLUMN IF EXISTS stripe_payment_intent_id")
    op.execute("ALTER TABLE event_registrations DROP COLUMN IF EXISTS stripe_checkout_session_id")
