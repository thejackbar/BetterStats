"""Per-club override for billing_checkout_enabled.

The platform-wide `billing_checkout_enabled` flag (migration 150 era,
platform_settings JSONB) is all-or-nothing — there was no way to let a single
test club through the real Stripe Checkout flow while every other club's
Primary Admin stayed on the stub. `organisations.billing_checkout_override`
adds a per-club three-state switch: NULL = follow the platform default,
TRUE = force-enabled for this club, FALSE = force-disabled for this club even
if the platform default is later switched on. See
services/platform_settings.billing_checkout_enabled_for_org.

Revision ID: 151
Revises: 150
Create Date: 2026-07-15
"""
from alembic import op


revision = '151'
down_revision = '150'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092.
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS billing_checkout_override BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS billing_checkout_override")
