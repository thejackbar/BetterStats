"""Stripe Product id cache for add-on subscription items.

Unlike a Checkout Session's line items (which support an inline ad-hoc
product via price_data.product_data), Stripe's SubscriptionItem.create and
Invoice.create_preview APIs require a real Product id when using price_data —
there's no inline product creation on those endpoints. Since a billable
module's name never changes, we create each Product ONCE and cache its id
here rather than re-creating (or searching for) it on every add-on checkout.
See services/stripe_client.py::_ensure_product.

Revision ID: 152
Revises: 151
Create Date: 2026-07-15
"""
from alembic import op


revision = '152'
down_revision = '151'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092.
    op.execute("""
        CREATE TABLE IF NOT EXISTS stripe_products (
            billing_key TEXT PRIMARY KEY,
            stripe_product_id TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_products")
