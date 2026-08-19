"""Stripe object caches remember which MODE (test/live) minted the id.

A Stripe Coupon, Product or Customer id belongs to ONE mode — a test-mode id
is simply not there when a live key asks for it ("No such coupon: 'IBBpUgf0';
a similar object exists in test mode, but a live mode key was used"). Both
BetterCricket caches (stripe_products from migration 152, stripe_coupons from
153) and discount_coupons.stripe_coupon_id were keyed with no idea of mode, so
every id created while the box ran test keys was handed straight to the live
API once the keys were switched — and every checkout carrying a discount
failed.

The cached ids carry no mode marker of their own, so rather than guess which
mode wrote an existing row, the backfill leaves them as 'unknown': a value no
live lookup will ever match, so the object is re-created in the current mode
the next time it's needed. The stale rows are left in place as history; the
handful of orphaned test-mode objects they point at cost nothing.

Revision ID: 263
Revises: 262
Create Date: 2026-08-19
"""
from alembic import op


revision = '263'
down_revision = '262'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092.
    op.execute("ALTER TABLE stripe_products ADD COLUMN IF NOT EXISTS stripe_mode TEXT NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE stripe_coupons ADD COLUMN IF NOT EXISTS stripe_mode TEXT NOT NULL DEFAULT 'unknown'")
    op.execute("ALTER TABLE discount_coupons ADD COLUMN IF NOT EXISTS stripe_mode TEXT")
    # The old single-column primary keys can't hold one row per mode. Dropped
    # in favour of a unique index on (key, mode), which is what the caches'
    # ON CONFLICT targets — a unique index serves that just as well as a PK.
    op.execute("""
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'stripe_products'::regclass AND contype = 'p'
            ) THEN
                ALTER TABLE stripe_products DROP CONSTRAINT stripe_products_pkey;
            END IF;
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conrelid = 'stripe_coupons'::regclass AND contype = 'p'
            ) THEN
                ALTER TABLE stripe_coupons DROP CONSTRAINT stripe_coupons_pkey;
            END IF;
        END $$;
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_products_key_mode "
        "ON stripe_products (billing_key, stripe_mode)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_stripe_coupons_cents_mode "
        "ON stripe_coupons (discount_cents, stripe_mode)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_stripe_products_key_mode")
    op.execute("DROP INDEX IF EXISTS uq_stripe_coupons_cents_mode")
    op.execute("ALTER TABLE stripe_products DROP COLUMN IF EXISTS stripe_mode")
    op.execute("ALTER TABLE stripe_coupons DROP COLUMN IF EXISTS stripe_mode")
    op.execute("ALTER TABLE discount_coupons DROP COLUMN IF EXISTS stripe_mode")
