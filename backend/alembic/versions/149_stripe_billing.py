"""Stripe billing (self-serve subscribe, Phase 1 — see
docs/self-serve-trial-onboarding-plan.md).

Adds the columns a Stripe Checkout Subscription needs to be linked back to a
club and a specific module: ``organisations.stripe_customer_id`` (one Stripe
Customer per club, reused across every Checkout session so a repeat visit
doesn't mint duplicates), and ``org_module_subscriptions.stripe_subscription_id``
/ ``stripe_subscription_item_id`` (a club's modules bought together are ONE
Stripe Subscription with one line item per module — the subscription id is
shared across those rows, the item id is what lets a webhook resolve exactly
which module row a given line item event belongs to).

Also adds ``stripe_webhook_events``, a dedupe ledger keyed on Stripe's own
event id — mirrors ``trial_lifecycle_nudges``'s dedupe shape (and SES's
``uq_email_event_dedupe``) so a redelivered webhook (Stripe retries
aggressively on anything but a 200) is a no-op rather than double-applying.

Revision ID: 149
Revises: 148
Create Date: 2026-07-14
"""
from alembic import op


revision = '149'
down_revision = '148'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092: the schema is layered (dump + lifespan +
    # alembic), so a plain ADD COLUMN/CREATE can hit an already-existing
    # object and abort `alembic upgrade head`, crash-looping the backend.
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_customer_id TEXT"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_organisations_stripe_customer_id "
        "ON organisations(stripe_customer_id) WHERE stripe_customer_id IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE org_module_subscriptions ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT"
    )
    op.execute(
        "ALTER TABLE org_module_subscriptions ADD COLUMN IF NOT EXISTS stripe_subscription_item_id TEXT"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_module_subscriptions_stripe_item "
        "ON org_module_subscriptions(stripe_subscription_item_id) WHERE stripe_subscription_item_id IS NOT NULL"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS stripe_webhook_events (
            event_id TEXT PRIMARY KEY,
            event_type TEXT NOT NULL,
            received_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS stripe_webhook_events")
    op.execute("DROP INDEX IF EXISTS uq_org_module_subscriptions_stripe_item")
    op.execute("ALTER TABLE org_module_subscriptions DROP COLUMN IF EXISTS stripe_subscription_item_id")
    op.execute("ALTER TABLE org_module_subscriptions DROP COLUMN IF EXISTS stripe_subscription_id")
    op.execute("DROP INDEX IF EXISTS uq_organisations_stripe_customer_id")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_customer_id")
