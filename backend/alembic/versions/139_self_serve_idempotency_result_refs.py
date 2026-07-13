"""Add org_id/user_id to self_serve_idempotency_keys.

Phase 9 (see docs/self-serve-trial-onboarding-plan.md) — once /submit actually
creates a club and admin account, a replayed submission (same idempotency key)
needs to return which club/user it created, not just a bare status string.
Nullable and additive; migration 138's rows (all status='validated', pre-Phase-9)
are unaffected.

Revision ID: 139
Revises: 138
Create Date: 2026-07-13
"""
from alembic import op


revision = '139'
down_revision = '138'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE self_serve_idempotency_keys ADD COLUMN IF NOT EXISTS org_id UUID")
    op.execute("ALTER TABLE self_serve_idempotency_keys ADD COLUMN IF NOT EXISTS user_id UUID")


def downgrade() -> None:
    op.execute("ALTER TABLE self_serve_idempotency_keys DROP COLUMN IF EXISTS user_id")
    op.execute("ALTER TABLE self_serve_idempotency_keys DROP COLUMN IF EXISTS org_id")
