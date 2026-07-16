"""BetterFees ← Xero: pull bank transactions for reconciliation.

A dedicated per-club Xero OAuth connection (`fee_xero_connections`) — unlike
Square, nothing else in the app uses this, so BetterFees owns the whole OAuth
handshake itself (see routers/fees.py + routers/public_xero.py). Read-only
(accounting.transactions.read scope only): pulls RECEIVE bank transactions
from one chosen bank account, fuzzy-matches them to a member the same way the
bank-statement CSV import does, and an admin confirms each match before it's
recorded as a fee payment (reusing the source/external_ref columns added on
fee_payments for the Square import). `fee_xero_import_log` mirrors
`fee_square_import_log` — a per-club resolved-events ledger (applied or
dismissed) so a dismissed transaction never resurfaces on the next preview.

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
    # alembic), so a plain CREATE can hit an already-existing object and abort
    # `alembic upgrade head`, crash-looping the backend.
    op.execute("""
        CREATE TABLE IF NOT EXISTS fee_xero_connections (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            tenant_id TEXT,
            tenant_name TEXT,
            access_token TEXT,
            refresh_token TEXT,
            token_expires_at TIMESTAMPTZ,
            scopes TEXT,
            bank_account_id TEXT,
            bank_account_name TEXT,
            sync_enabled BOOLEAN NOT NULL DEFAULT false,
            last_sync_at TIMESTAMPTZ,
            last_sync_status TEXT,
            last_sync_error TEXT,
            connected_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            connected_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fee_xero_org UNIQUE (organisation_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS fee_xero_import_log (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            external_ref TEXT NOT NULL,
            status TEXT NOT NULL,
            fee_payment_id UUID REFERENCES fee_payments(id) ON DELETE SET NULL,
            description TEXT,
            amount NUMERIC(10, 2),
            occurred_at DATE,
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_fee_xero_import_log_ref UNIQUE (organisation_id, external_ref)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS fee_xero_import_log")
    op.execute("DROP TABLE IF EXISTS fee_xero_connections")
