"""Self-serve trial registration: email verification codes.

New table for the OTP flow (Phase 6, see docs/self-serve-trial-onboarding-plan.md).
Only the bcrypt hash of the 4-digit code is stored, never the code itself. One row
per code issued; a fresh send supersedes any earlier unverified row for the same
email so only the latest is ever valid.

Revision ID: 136
Revises: 135
Create Date: 2026-07-13
"""
from alembic import op


revision = '136'
down_revision = '135'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS self_serve_email_verifications (
            id UUID PRIMARY KEY,
            email TEXT NOT NULL,
            code_hash TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ NOT NULL,
            verified_at TIMESTAMPTZ,
            superseded_at TIMESTAMPTZ,
            attempt_count INTEGER NOT NULL DEFAULT 0
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_self_serve_email_verifications_email
        ON self_serve_email_verifications(email)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS self_serve_email_verifications")
