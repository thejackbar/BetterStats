"""Teamwear ordering (migration 402): the one copy of its DDL.

Alembic's 402 and the ``main.py`` lifespan both run ``STATEMENTS``, so every
statement is idempotent (``IF NOT EXISTS`` everywhere, no bare inserts).

The shop range IS the BetterMerch stock register: a teamwear product is a
``merch_products`` row with its sizes as ``merch_variants`` (so spare kit from a
campaign lands in club stock as ordinary stock). What teamwear adds about a
product lives beside it in ``teamwear_products`` rather than as new columns on
the ORM-mapped ``merch_products`` (rule 9: a raw column there would have to be
mapped too).

Nothing here stores a total, a balance or a paid status: an order's total is its
active lines, its balance is that minus its live payments, and both are read
fresh every time (CLAUDE.md rule 4). Payments are never deleted, only voided.
"""

STATEMENTS: list[str] = [
    # Club settings: the price rule, the bank details members pay into, the
    # reference pattern, and the default reminder schedule.
    """
    CREATE TABLE IF NOT EXISTS teamwear_settings (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        markup_pct NUMERIC(6,2) NOT NULL DEFAULT 10,
        round_to NUMERIC(8,2) NOT NULL DEFAULT 1,
        default_moq INTEGER NOT NULL DEFAULT 10,
        cut_ratio INTEGER NOT NULL DEFAULT 9,
        supplier_name TEXT NOT NULL DEFAULT 'Masuri',
        bank_account_name TEXT,
        bank_bsb TEXT,
        bank_account_number TEXT,
        reference_suffix TEXT NOT NULL DEFAULT 'TEAMWEAR',
        coordinator_name TEXT,
        coordinator_email TEXT,
        pay_days INTEGER NOT NULL DEFAULT 14,
        reminder_offsets TEXT NOT NULL DEFAULT '-3,0,3',
        card_stripe BOOLEAN NOT NULL DEFAULT true,
        card_square BOOLEAN NOT NULL DEFAULT true,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # What teamwear knows about a stock-register product.
    """
    CREATE TABLE IF NOT EXISTS teamwear_products (
        product_id UUID PRIMARY KEY REFERENCES merch_products(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        supplier_code TEXT,
        rrp NUMERIC(10,2),
        price_override NUMERIC(10,2),
        made_to_order BOOLEAN NOT NULL DEFAULT true,
        personalisation TEXT NOT NULL DEFAULT 'none',
        moq INTEGER,
        in_shop BOOLEAN NOT NULL DEFAULT true,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_products_org ON teamwear_products(organisation_id)",
    # Product photos: decoded, shrunk and re-encoded before they are stored.
    """
    CREATE TABLE IF NOT EXISTS teamwear_images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES merch_products(id) ON DELETE CASCADE,
        mime TEXT NOT NULL,
        data BYTEA NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_images_product ON teamwear_images(product_id, sort_order)",
    # One order round.
    """
    CREATE TABLE IF NOT EXISTS teamwear_campaigns (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        intro TEXT,
        stage TEXT NOT NULL DEFAULT 'draft',
        opens_on DATE,
        closes_at TIMESTAMPTZ,
        pay_due_on DATE,
        reminder_offsets TEXT,
        moq INTEGER,
        launched_at TIMESTAMPTZ,
        approved_on DATE,
        approval_note TEXT,
        approval_recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
        approval_recorded_at TIMESTAMPTZ,
        approved_plan TEXT,
        payment_requested_at TIMESTAMPTZ,
        exported_at TIMESTAMPTZ,
        exported_by UUID REFERENCES users(id) ON DELETE SET NULL,
        deposit_paid_on DATE,
        balance_paid_on DATE,
        received_at TIMESTAMPTZ,
        arrival_emailed_at TIMESTAMPTZ,
        closed_at TIMESTAMPTZ,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_campaigns_org ON teamwear_campaigns(organisation_id, created_at DESC)",
    # The products a campaign offers, with the price it was offered at.
    """
    CREATE TABLE IF NOT EXISTS teamwear_campaign_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        campaign_id UUID NOT NULL REFERENCES teamwear_campaigns(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES merch_products(id) ON DELETE CASCADE,
        price NUMERIC(10,2) NOT NULL,
        decision TEXT NOT NULL DEFAULT 'hold',
        decision_note TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        CONSTRAINT uq_teamwear_campaign_item UNIQUE (campaign_id, product_id)
    )
    """,
    # Units the club adds by size to reach the supplier's minimum (they go to club stock).
    """
    CREATE TABLE IF NOT EXISTS teamwear_topups (
        campaign_id UUID NOT NULL REFERENCES teamwear_campaigns(id) ON DELETE CASCADE,
        variant_id UUID NOT NULL REFERENCES merch_variants(id) ON DELETE CASCADE,
        product_id UUID NOT NULL REFERENCES merch_products(id) ON DELETE CASCADE,
        qty INTEGER NOT NULL DEFAULT 0,
        received_to_stock_at TIMESTAMPTZ,
        PRIMARY KEY (campaign_id, variant_id)
    )
    """,
    # A member's order. campaign_id NULL is an order of in-stock items from the shop.
    """
    CREATE TABLE IF NOT EXISTS teamwear_orders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        campaign_id UUID REFERENCES teamwear_campaigns(id) ON DELETE CASCADE,
        placed_by_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
        contact_name TEXT NOT NULL,
        contact_email TEXT,
        contact_phone TEXT,
        reference TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'submitted',
        source TEXT NOT NULL DEFAULT 'member',
        notes TEXT,
        payment_requested_at TIMESTAMPTZ,
        due_on DATE,
        unpaid_decision TEXT,
        unpaid_note TEXT,
        packed_at TIMESTAMPTZ,
        collected_at TIMESTAMPTZ,
        cancelled_reason TEXT,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_orders_campaign ON teamwear_orders(campaign_id)",
    "CREATE INDEX IF NOT EXISTS ix_teamwear_orders_org ON teamwear_orders(organisation_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_teamwear_orders_player ON teamwear_orders(placed_by_player_id)",
    # One line per garment for a personalised product (qty 1), else per size.
    """
    CREATE TABLE IF NOT EXISTS teamwear_order_lines (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        order_id UUID NOT NULL REFERENCES teamwear_orders(id) ON DELETE CASCADE,
        product_id UUID REFERENCES merch_products(id) ON DELETE SET NULL,
        variant_id UUID REFERENCES merch_variants(id) ON DELETE SET NULL,
        product_name TEXT NOT NULL,
        supplier_code TEXT,
        size_label TEXT,
        unit_price NUMERIC(10,2) NOT NULL DEFAULT 0,
        qty INTEGER NOT NULL DEFAULT 1,
        wearer_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
        wearer_name TEXT,
        personal_number TEXT,
        personal_text TEXT,
        number_status TEXT,
        number_note TEXT,
        state TEXT NOT NULL DEFAULT 'active',
        cut_by_triage BOOLEAN NOT NULL DEFAULT false,
        club_covered BOOLEAN NOT NULL DEFAULT false,
        covered_reason TEXT,
        from_stock BOOLEAN NOT NULL DEFAULT false,
        issued_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_lines_order ON teamwear_order_lines(order_id)",
    "CREATE INDEX IF NOT EXISTS ix_teamwear_lines_wearer ON teamwear_order_lines(wearer_player_id)",
    # Money in. Never deleted: a mistake is voided.
    """
    CREATE TABLE IF NOT EXISTS teamwear_payments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        order_id UUID NOT NULL REFERENCES teamwear_orders(id) ON DELETE CASCADE,
        amount NUMERIC(10,2) NOT NULL,
        method TEXT NOT NULL DEFAULT 'bank',
        source TEXT NOT NULL DEFAULT 'manual',
        paid_on DATE NOT NULL DEFAULT CURRENT_DATE,
        reference TEXT,
        external_ref TEXT,
        note TEXT,
        recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
        voided_at TIMESTAMPTZ,
        void_reason TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_payments_order ON teamwear_payments(order_id)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_teamwear_payments_ext
        ON teamwear_payments(organisation_id, external_ref)
        WHERE external_ref IS NOT NULL AND voided_at IS NULL
    """,
    # A card checkout started from the member's page (Stripe Checkout or a Square payment link).
    """
    CREATE TABLE IF NOT EXISTS teamwear_checkouts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        order_id UUID NOT NULL REFERENCES teamwear_orders(id) ON DELETE CASCADE,
        provider TEXT NOT NULL,
        external_id TEXT,
        provider_order_id TEXT,
        url TEXT,
        amount NUMERIC(10,2) NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        completed_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_checkouts_order ON teamwear_checkouts(order_id)",
    # A member asking for a change once the order is confirmed.
    """
    CREATE TABLE IF NOT EXISTS teamwear_change_requests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        order_id UUID NOT NULL REFERENCES teamwear_orders(id) ON DELETE CASCADE,
        requested_by_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
        message TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        response TEXT,
        resolved_by UUID REFERENCES users(id) ON DELETE SET NULL,
        resolved_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_changes_order ON teamwear_change_requests(order_id)",
    # Every email teamwear tried to send. The unique key stops a reminder going twice.
    """
    CREATE TABLE IF NOT EXISTS teamwear_emails (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        campaign_id UUID REFERENCES teamwear_campaigns(id) ON DELETE CASCADE,
        order_id UUID REFERENCES teamwear_orders(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        dedupe_key TEXT,
        to_email TEXT,
        status TEXT NOT NULL,
        detail TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_teamwear_emails_campaign ON teamwear_emails(campaign_id, created_at DESC)",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_teamwear_emails_dedupe
        ON teamwear_emails(organisation_id, dedupe_key)
        WHERE dedupe_key IS NOT NULL AND status = 'sent'
    """,
    # Square: a connection made before teamwear card payments asked only for read scopes.
    "ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS can_take_payments BOOLEAN NOT NULL DEFAULT false",
]

# Tables in the order a downgrade drops them (children first). Every one is owned by 402.
TABLES_402 = [
    "teamwear_emails", "teamwear_change_requests", "teamwear_checkouts", "teamwear_payments",
    "teamwear_order_lines", "teamwear_orders", "teamwear_topups", "teamwear_campaign_items",
    "teamwear_campaigns", "teamwear_images", "teamwear_products", "teamwear_settings",
]
DOWNGRADE_402 = [f"DROP TABLE IF EXISTS {t}" for t in TABLES_402] + [
    "ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS can_take_payments",
]
