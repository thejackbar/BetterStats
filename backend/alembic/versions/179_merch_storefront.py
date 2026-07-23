"""Merch storefront — public online ordering against BetterMerch stock.

Reuses the existing BetterMerch catalogue (merch_products/merch_variants)
rather than a parallel product model — a product is storefront-eligible
when it's for_resale, active, ``show_in_storefront`` (new column, default
true so an existing club's whole resale catalogue is visible the moment
they're switched on) and NOT Square-synced (source='manual') — a
Square-synced line stays admin/POS-only, since Square's daily reconcile
sets an ABSOLUTE stock count from the till and would silently overwrite an
online sale it doesn't know about.

Off by default, same flag shape as the member portal (migration 178):
platform_settings.merch_storefront_enabled + organisations.
merch_storefront_override — invisible to every club admin and unusable by
any real customer until a super admin switches it on globally or for one
test club.

Checkout reuses the SAME per-club Stripe Connect account the member portal
uses for fee payments (organisations.stripe_connect_account_id, migration
178) — one club, one connected Stripe account, for member fees AND merch
sales alike.

merch_orders/merch_order_items are a NEW pair of tables (not a repurposing
of merch_movements) since an order needs its own customer/contact details,
payment status and Stripe correlation that a stock movement row has no
place for; a paid order's line items are turned into ordinary
merch_movements (kind='sold', source='online_store') via the existing
record_movement() once payment is confirmed, so stock accounting stays in
the one place it's always lived.

Revision ID: 179
Revises: 178
Create Date: 2026-07-23
"""
from alembic import op

revision = '179'
down_revision = '178'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE merch_products ADD COLUMN IF NOT EXISTS show_in_storefront BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS merch_storefront_override BOOLEAN")

    op.execute("""
        CREATE TABLE IF NOT EXISTS merch_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            customer_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            status TEXT NOT NULL DEFAULT 'pending_payment',
            total_cents INTEGER NOT NULL DEFAULT 0,
            stripe_checkout_session_id TEXT,
            stripe_payment_intent_id TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_merch_orders_org ON merch_orders(organisation_id, status)")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_merch_orders_checkout_session "
        "ON merch_orders(stripe_checkout_session_id) WHERE stripe_checkout_session_id IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS merch_order_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES merch_orders(id) ON DELETE CASCADE,
            variant_id UUID REFERENCES merch_variants(id) ON DELETE SET NULL,
            product_name TEXT NOT NULL,
            variant_label TEXT,
            unit_price_cents INTEGER NOT NULL DEFAULT 0,
            quantity INTEGER NOT NULL DEFAULT 1
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_merch_order_items_order ON merch_order_items(order_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS merch_order_items")
    op.execute("DROP TABLE IF EXISTS merch_orders")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS merch_storefront_override")
    op.execute("ALTER TABLE merch_products DROP COLUMN IF EXISTS show_in_storefront")
