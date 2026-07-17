"""Discount breakdown + payment method on billing_invoices.

Stripe's own invoice can only show ONE combined discount line (Checkout
Session's `discounts` param is capped at one element — see
stripe_client.create_checkout_session's docstring), so it can't itemise a
bundle discount and a coupon-code discount separately. BetterCricket's own
billing_invoices row now carries the TRUE separate breakdown regardless
(bundle_discount_cents, coupon_code, coupon_discount_cents) — computed
locally at checkout time and round-tripped through the Checkout Session's
metadata, read back by stripe_billing._upsert_invoice — powering the
Account page's expanded Billing History rows and the Super Admin discount
usage reports.

payment_method_type/payment_method_summary record which payment method
actually paid the invoice (e.g. "Visa Debit •••• 4242", "PayTo (...0400)"),
fetched from the invoice's PaymentIntent at the same point.

Revision ID: 159
Revises: 158
Create Date: 2026-07-17
"""
from alembic import op


revision = '159'
down_revision = '158'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS bundle_discount_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS coupon_code TEXT")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS coupon_discount_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_method_type TEXT")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS payment_method_summary TEXT")
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_billing_invoices_coupon_code ON billing_invoices(coupon_code) "
        "WHERE coupon_code IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_billing_invoices_coupon_code")
    op.execute("ALTER TABLE billing_invoices DROP COLUMN IF EXISTS payment_method_summary")
    op.execute("ALTER TABLE billing_invoices DROP COLUMN IF EXISTS payment_method_type")
    op.execute("ALTER TABLE billing_invoices DROP COLUMN IF EXISTS coupon_discount_cents")
    op.execute("ALTER TABLE billing_invoices DROP COLUMN IF EXISTS coupon_code")
    op.execute("ALTER TABLE billing_invoices DROP COLUMN IF EXISTS bundle_discount_cents")
