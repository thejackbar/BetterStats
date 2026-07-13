"""Self-serve trial registration: idempotency keys for final submission.

Phase 8 (see docs/self-serve-trial-onboarding-plan.md) — the safety rail
around the eventual atomic registration transaction (Phase 9). The key
itself is the primary key: a repeat submission with the same key is
recognised and never reprocessed, so a double-click, browser refresh, or
network retry can't create duplicate clubs/users/trials once Phase 9 lands.

Revision ID: 138
Revises: 137
Create Date: 2026-07-13
"""
from alembic import op


revision = '138'
down_revision = '137'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS self_serve_idempotency_keys (
            idempotency_key TEXT PRIMARY KEY,
            email TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'validated',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS self_serve_idempotency_keys")
