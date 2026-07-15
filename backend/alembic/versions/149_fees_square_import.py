"""BetterFees ← Square: import completed Square sales as fee payments.

Reuses BetterMerch's existing per-club Square OAuth connection (one Square
account per club, shared across modules) — no new OAuth flow. Adds the
fee-matching config to `merch_square_connections` (`sync_fees`,
`fee_item_keywords`, its own `fees_last_sync_*` trio so a fees-side failure
doesn't clobber merch's own last-sync status), a `source`/`external_ref` pair
on `fee_payments` (mirrors `merch_movements`' dedupe pattern) so a re-run never
double-imports a sale, and `fee_square_import_log` — a per-club resolved-events
ledger (applied or dismissed) keyed by `external_ref` so a dismissed Square
sale (e.g. a canteen item that happened to match a keyword) never resurfaces in
the review queue.

Revision ID: 149
Revises: 148
Create Date: 2026-07-15
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
    op.execute("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS sync_fees BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fee_item_keywords TEXT")
    op.execute("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_at TIMESTAMPTZ")
    op.execute("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_status TEXT")
    op.execute("ALTER TABLE merch_square_connections ADD COLUMN IF NOT EXISTS fees_last_sync_error TEXT")

    op.execute("ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'")
    op.execute("ALTER TABLE fee_payments ADD COLUMN IF NOT EXISTS external_ref TEXT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_fee_payment_external_ref "
        "ON fee_payments(organisation_id, external_ref) WHERE external_ref IS NOT NULL"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS fee_square_import_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            external_ref TEXT NOT NULL,
            status TEXT NOT NULL,
            fee_payment_id UUID REFERENCES fee_payments(id) ON DELETE SET NULL,
            item_name TEXT,
            note TEXT,
            amount NUMERIC(10, 2),
            occurred_at DATE,
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fee_square_import_log_ref UNIQUE (organisation_id, external_ref)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fee_square_import_log")
    op.execute("DROP INDEX IF EXISTS uq_fee_payment_external_ref")
    op.execute("ALTER TABLE fee_payments DROP COLUMN IF EXISTS external_ref")
    op.execute("ALTER TABLE fee_payments DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS fees_last_sync_error")
    op.execute("ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS fees_last_sync_status")
    op.execute("ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS fees_last_sync_at")
    op.execute("ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS fee_item_keywords")
    op.execute("ALTER TABLE merch_square_connections DROP COLUMN IF EXISTS sync_fees")
