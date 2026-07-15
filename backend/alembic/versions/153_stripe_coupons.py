"""Stripe Coupon id cache for the bundle discount.

Every checkout attempt used to mint a brand-new Stripe Coupon for the bundle
discount, even for the exact same dollar amount — cluttering the Dashboard
with duplicates and making "Redemptions" per coupon meaningless. Mirrors
migration 152's stripe_products cache: one Coupon per distinct discount
amount, created once and reused. See
services/stripe_client.py::_ensure_bundle_coupon.

Also the point this shipped: the bundle coupon's duration changed from
`forever` (discounted every renewal indefinitely) to `once` (the initial
subscribe only — a renewal is full price unless a fresh coupon is applied to
it) — this migration doesn't touch that, it's a pure code change, but the two
shipped together.

Revision ID: 153
Revises: 152
Create Date: 2026-07-15
"""
from alembic import op


revision = '153'
down_revision = '152'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092.
    op.execute("""
        CREATE TABLE IF NOT EXISTS stripe_coupons (
            discount_cents INTEGER PRIMARY KEY,
            stripe_coupon_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_coupons")
