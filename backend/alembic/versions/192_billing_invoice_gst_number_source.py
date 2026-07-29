"""Billing invoices — GST amount, invoice number, and source.

The Super Admin financial-management page drills into each invoice and shows
its Stripe invoice number, the GST that was charged, and whether the invoice
came from a normal subscription renewal or was raised on the club's behalf by
a super admin (a shareable send-invoice, or a checkout entered for them). None
of those three were captured on billing_invoices before — the GST amount in
particular is only knowable from Stripe's own ``invoice.tax``, so recording it
at upsert time avoids a live Stripe call per row when the page lists history.

Additive and idempotent (mirrored in main.py's lifespan). ``tax_cents``
defaults 0 so existing rows read as "no GST recorded" rather than NULL; the
other two are nullable.

Revision ID: 192
Revises: 191
Create Date: 2026-07-29
"""
from alembic import op

revision = '192'
down_revision = '191'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS invoice_number TEXT")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS tax_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS source TEXT")


def downgrade() -> None:
    for col in ("invoice_number", "tax_cents", "source"):
        op.execute(f"ALTER TABLE billing_invoices DROP COLUMN IF EXISTS {col}")
