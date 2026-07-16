"""BetterCricket-managed discount coupons.

A Super-Admin-only coupon catalogue, entirely owned by BetterCricket — every
eligibility rule (module coverage, redemption window, new-signup vs loyalty
window, duration, max redemptions, stackability with the bundle discount)
lives in these tables and is enforced by services/discount_coupons.py before
BetterCricket ever talks to Stripe. The corresponding Stripe Coupon object is
a pure sync target (services/stripe_client.sync_coupon_to_stripe) — Super
Admin never edits a Coupon by hand in the Stripe Dashboard for this.

discount_coupon_redemptions is the audit trail AND the "one live redemption
per club per coupon" enforcement (a partial unique index on non-revoked rows,
so a Super Admin's revoke frees the slot for a genuine mistake).

Revision ID: 156
Revises: 155
Create Date: 2026-07-16
"""
from alembic import op


revision = '156'
down_revision = '155'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092.
    op.execute("""
        CREATE TABLE IF NOT EXISTS discount_coupons (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            code TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL,
            discount_type TEXT NOT NULL,
            discount_value NUMERIC NOT NULL,
            module_keys JSONB,
            redeem_window_start DATE,
            redeem_window_end DATE,
            new_signup_window_start DATE,
            new_signup_window_end DATE,
            loyalty_window_start DATE,
            loyalty_window_end DATE,
            duration_mode TEXT NOT NULL DEFAULT 'once',
            duration_renewals INTEGER,
            stackable_with_bundle BOOLEAN NOT NULL DEFAULT false,
            max_redemptions INTEGER,
            active BOOLEAN NOT NULL DEFAULT true,
            stripe_coupon_id TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS discount_coupon_redemptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            coupon_id UUID NOT NULL REFERENCES discount_coupons(id) ON DELETE CASCADE,
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            redeemed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            applied_via TEXT NOT NULL,
            redeemed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            stripe_subscription_id TEXT,
            status TEXT NOT NULL DEFAULT 'active'
        )
    """)
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_coupon_redemption_live_slot
        ON discount_coupon_redemptions (coupon_id, organisation_id)
        WHERE status <> 'revoked'
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_coupon_redemptions_coupon "
        "ON discount_coupon_redemptions(coupon_id, redeemed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS discount_coupon_redemptions")
    op.execute("DROP TABLE IF EXISTS discount_coupons")
