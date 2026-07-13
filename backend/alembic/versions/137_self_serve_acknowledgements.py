"""Self-serve trial registration: legal acknowledgements.

Phase 7 (see docs/self-serve-trial-onboarding-plan.md) — Terms of Service,
Privacy Policy and the club-authority statement, versioned and audited. Keyed by
email (no user/org exists yet at this point in registration, same as the email
verification table added in migration 136).

Revision ID: 137
Revises: 136
Create Date: 2026-07-13
"""
from alembic import op


revision = '137'
down_revision = '136'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS self_serve_acknowledgements (
            id UUID PRIMARY KEY,
            email TEXT NOT NULL,
            club_name TEXT NOT NULL,
            terms_version TEXT NOT NULL,
            privacy_version TEXT NOT NULL,
            accepted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            ip_hash TEXT,
            user_agent TEXT
        )
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_self_serve_acknowledgements_email
        ON self_serve_acknowledgements(email)
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS self_serve_acknowledgements")
