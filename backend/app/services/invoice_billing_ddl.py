"""Schema for BetterCricket's own annual invoicing (migration 308).

The ONE copy of these statements — alembic's 308 and the ``main.py`` lifespan
mirror both run this list, in this order, per the ``vote_medal_ddl`` rule. Every
statement is idempotent because the lifespan re-runs the whole list on every
boot.
"""

STATEMENTS = [
    # How a club pays: 'card' (Stripe Checkout + Stripe Subscription, the flow
    # every club is on today, so that is the default) or 'invoice'.
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS billing_method TEXT NOT NULL DEFAULT 'card'",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS billing_method_changed_at TIMESTAMPTZ",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS billing_method_changed_by UUID",
    # Whether the club is OFFERED invoice billing at all. Off for every club,
    # including every club created from now on: paying by card through Stripe
    # is the default, and only a Super Admin can switch invoicing on for a
    # club from All Clubs (per direct instruction).
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS invoice_billing_enabled BOOLEAN NOT NULL DEFAULT false",
    # What is paying for a module's current period. NULL for every row written
    # before this, which is right: nothing has been invoice-billed yet, and a
    # NULL row is never renewed or lapsed by the invoice job.
    "ALTER TABLE org_module_subscriptions ADD COLUMN IF NOT EXISTS billing_source TEXT",
    # A card club's existing paid modules are carried by its Stripe
    # Subscription. Stamped so a later switch to invoice billing can never
    # mistake them for modules it should invoice.
    """
    UPDATE org_module_subscriptions s SET billing_source = 'stripe'
      FROM organisations o
     WHERE o.id = s.organisation_id
       AND o.stripe_subscription_id IS NOT NULL
       AND s.status IN ('active', 'past_due')
       AND s.billing_source IS NULL
    """,
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS billing_method TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS invoice_kind TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS invoice_number TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS billing_keys JSONB",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS service_start_date DATE",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS service_end_date DATE",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS due_at TIMESTAMPTZ",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS amount_total_cents INTEGER",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS pay_token TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS sent_to_email TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS emailed_at TIMESTAMPTZ",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS email_error TEXT",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS issued_by_user_id UUID",
    "ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS coupon_redemption_id UUID",
    # The pay link in an email resolves on this, so it must be unique.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_invoices_pay_token
        ON billing_invoices (pay_token) WHERE pay_token IS NOT NULL
    """,
    # One live renewal invoice per club per period. The renewal job checks
    # before it creates, and this is what stops two overlapping runs both
    # getting through that check — the loser voids the Stripe invoice it made.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_billing_invoices_renewal_period
        ON billing_invoices (organisation_id, service_start_date)
     WHERE invoice_kind = 'renewal' AND status NOT IN ('void', 'uncollectible')
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_billing_invoices_org_open
        ON billing_invoices (organisation_id) WHERE status = 'open'
    """,
]

DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_billing_invoices_org_open",
    "DROP INDEX IF EXISTS uq_billing_invoices_renewal_period",
    "DROP INDEX IF EXISTS uq_billing_invoices_pay_token",
    *[
        f"ALTER TABLE billing_invoices DROP COLUMN IF EXISTS {c}"
        for c in (
            "coupon_redemption_id", "issued_by_user_id", "email_error", "emailed_at",
            "sent_to_email", "pay_token", "amount_total_cents", "due_at", "service_end_date",
            "service_start_date", "billing_keys", "invoice_number", "invoice_kind", "billing_method",
        )
    ],
    "ALTER TABLE org_module_subscriptions DROP COLUMN IF EXISTS billing_source",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS invoice_billing_enabled",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS billing_method_changed_by",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS billing_method_changed_at",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS billing_method",
]
