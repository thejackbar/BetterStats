"""Stripe Checkout — recurring subscription billing.

Adds ``organisations.stripe_customer_id``/``.stripe_subscription_id`` (set by
the /public/stripe/webhook handler once a Primary Admin completes a real
checkout — one Stripe Customer/Subscription per club, covering every module it
holds via Stripe) and ``billing_invoices`` (a local mirror of each Stripe
Invoice event, so the Account page's billing history never has to call the
Stripe API directly). Entitlement itself still lives entirely in
``org_module_subscriptions`` (migration 118) — a successful Stripe payment
just calls the same ``services/module_subscriptions.set_status_billing``
writer the existing super-admin "approve subscribe request" flow already uses.

Gated behind ``platform_settings.billing_checkout_enabled`` (no migration
needed for that — see the JSONB settings blob, migration 120) — this schema
can ship well before the flag (or real Stripe keys) are switched on.

Revision ID: 150
Revises: 149
Create Date: 2026-07-15
"""
from alembic import op


revision = '150'
down_revision = '149'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092: the schema is layered (dump + lifespan +
    # alembic), so a plain ADD COLUMN/CREATE can hit an already-existing
    # object and abort `alembic upgrade head`, crash-looping the backend.
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT")

    op.execute("""
        CREATE TABLE IF NOT EXISTS billing_invoices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            stripe_invoice_id TEXT NOT NULL,
            stripe_subscription_id TEXT,
            status TEXT NOT NULL,
            amount_due INTEGER NOT NULL DEFAULT 0,
            amount_paid INTEGER NOT NULL DEFAULT 0,
            currency TEXT NOT NULL DEFAULT 'aud',
            period_start TIMESTAMPTZ,
            period_end TIMESTAMPTZ,
            hosted_invoice_url TEXT,
            invoice_pdf TEXT,
            line_items JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_billing_invoices_stripe_id UNIQUE (stripe_invoice_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_billing_invoices_org "
        "ON billing_invoices(organisation_id, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS billing_invoices")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_subscription_id")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_customer_id")
