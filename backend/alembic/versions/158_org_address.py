"""Club address on organisations, for Stripe Tax + general club info.

Stripe's automatic tax calculation needs an address on the Customer to know
which jurisdiction to tax — a Checkout Session that passes an explicit
customer (every session does now, see stripe_client._ensure_customer)
rejects outright without one ("Automatic tax calculation in Checkout
requires a valid address on the Customer"). Self-serve registration resolves
the club's real address (PlayHQ public directory first, falling back to the
already-crawled Club Directory / marketing_clubs) and stores it here, so the
Stripe Customer can be created with a real address from the first checkout
attempt rather than depending on the payer typing one in.

Mirrors marketing_clubs' address columns for consistency.

Revision ID: 158
Revises: 157
Create Date: 2026-07-16
"""
from alembic import op


revision = '158'
down_revision = '157'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS address_line1 TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS suburb TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS state TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS postcode TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS country TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS address_line1")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS suburb")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS state")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS postcode")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS country")
