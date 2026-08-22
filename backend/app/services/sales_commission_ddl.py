"""Migration 277's schema, in ONE copy run by both alembic and the lifespan
mirror in ``main.py`` — the rule ``vote_medal_ddl`` / ``pillar_plan_ddl`` /
``plan_tree_ddl`` already set. Every statement is idempotent, because the
lifespan re-runs the whole list on every boot.

A rep's commission is a percentage of the deal value they EARNED
(``crm_deals.commission_rep_user_id``, migration 264 — who did the sales work,
not who happens to hold the club now).

* ``sales_commission_rates`` — the percentage. One row per rep, plus ONE row
  with a NULL ``user_id`` that is the platform default a rep with no row of
  their own falls back to. Seeded at 0, deliberately: a commission percentage
  is a commercial decision, and a number invented here would be quoted back at
  us, so the screen asks for one rather than pretending to know it.

* ``crm_deals.commission_rate_percent`` — the rate STAMPED at the moment the
  deal was won. Changing the rate afterwards must not silently rewrite what a
  rep already earned last quarter; the forecast over OPEN deals reads the LIVE
  rate, because a forecast is about what is still to come. Deliberately NOT a
  snapshot of the deal's VALUE: correcting a mis-recorded won deal should flow
  through to the commission on it, which is the opposite of what a rate change
  should do.

* ``sales_commission_payments`` — what has actually been paid out, per rep.
  Commission due is earned minus paid, so a payment is the only thing that
  brings it down.

Migration 278 moves EARNED commission off the CRM deal and onto the Stripe
payment, per direct instruction: a deal's stage is a human judgement somebody
can drag around, and a confirmed Stripe payment is a fact. The commissionable
columns therefore live on ``billing_invoices``, our own mirror of each Stripe
invoice, and are stamped at the moment the payment is recorded — the rep who
earned the club and the rate that applied that day, so changing a rate later
cannot rewrite what a payment already earned.

Only NEW BUSINESS earns: Stripe's own ``billing_reason`` says which. An
invoice created by the initial subscribe (``subscription_create``) or by
adding modules to a live subscription (``subscription_update``) is new
business; a renewal of what the club already holds (``subscription_cycle``)
is not, and earns nothing. Commission is calculated on the amount NET OF GST
— tax collected on our behalf was never revenue.
"""

SALES_COMMISSION_SQL = [
    """
    CREATE TABLE IF NOT EXISTS sales_commission_rates (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        user_id UUID REFERENCES users(id) ON DELETE CASCADE,
        rate_percent NUMERIC(6,3) NOT NULL DEFAULT 0,
        updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # One rate per rep, and exactly one platform default. Two partial uniques
    # rather than a plain UNIQUE(user_id), which would let any number of NULL
    # rows through — several rows each claiming to be "the default" is the one
    # state this table must not be able to hold.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_commission_rates_user
    ON sales_commission_rates (user_id) WHERE user_id IS NOT NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_sales_commission_rates_default
    ON sales_commission_rates ((user_id IS NULL)) WHERE user_id IS NULL
    """,
    # The id is supplied explicitly rather than left to the column default,
    # and that is load-bearing: ``Base.metadata.create_all`` runs FIRST in the
    # lifespan and creates this table from the ORM model, whose id default is
    # Python-side — so the CREATE TABLE above is a no-op and the column has no
    # server default to fall back on. Caught by running the real boot order
    # against a real Postgres, where this seed failed outright.
    """
    INSERT INTO sales_commission_rates (id, user_id, rate_percent)
    SELECT gen_random_uuid(), NULL, 0
    WHERE NOT EXISTS (SELECT 1 FROM sales_commission_rates WHERE user_id IS NULL)
    """,
    """
    ALTER TABLE crm_deals ADD COLUMN IF NOT EXISTS commission_rate_percent NUMERIC(6,3)
    """,
    """
    CREATE TABLE IF NOT EXISTS sales_commission_payments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        rep_user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        amount_cents BIGINT NOT NULL,
        paid_on DATE NOT NULL,
        reference TEXT,
        note TEXT,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_sales_commission_payments_rep
    ON sales_commission_payments (rep_user_id, paid_on DESC)
    """,
    # ── Migration 278: earned commission rides on the Stripe payment ──────
    # Stripe's own reason the invoice exists: subscription_create (the first
    # payment), subscription_update (modules added to a live subscription),
    # subscription_cycle (a renewal). This is what separates new business from
    # a renewal, rather than us inferring it from line items.
    """ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS billing_reason TEXT""",
    # What the club paid NET OF GST — Stripe's total_excluding_tax. amount_paid
    # includes tax, which was never our revenue and must not be commissioned.
    # NULL on every invoice recorded before this shipped; app.scripts.
    # backfill_invoice_commission fills those in from Stripe.
    """ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS amount_ex_tax_cents INTEGER""",
    # Stamped when the payment is recorded, never recomputed: who earned the
    # club, the rate that applied that day, and the resulting commission.
    # commission_kind is 'initial' | 'expansion', or NULL for a payment that
    # earns nothing (a renewal, a credit, an unattributed club).
    """
    ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS
    commission_rep_user_id UUID REFERENCES users(id) ON DELETE SET NULL
    """,
    """ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS commission_rate_percent NUMERIC(6,3)""",
    """ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS commission_cents BIGINT""",
    """ALTER TABLE billing_invoices ADD COLUMN IF NOT EXISTS commission_kind TEXT""",
    """
    CREATE INDEX IF NOT EXISTS ix_billing_invoices_commission_rep
    ON billing_invoices (commission_rep_user_id)
    WHERE commission_rep_user_id IS NOT NULL
    """,
]
