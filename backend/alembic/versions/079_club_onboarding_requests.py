"""Club onboarding requests (public Contact-form submissions).

Stores every submission from the marketing Contact form
(betterat.cricket/contact) so prospective-club enquiries are tracked in the
super-admin area, alongside the Formspree email the form still sends. Public and
unauthenticated: no organisation_id, no user. Additive and idempotent.

Revision ID: 079
Revises: 078
Create Date: 2026-06-10

"""
from alembic import op


revision = '079'
down_revision = '078'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_onboarding_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            club TEXT NOT NULL,
            email TEXT NOT NULL,
            phone TEXT,
            association TEXT,
            grades TEXT,
            storage TEXT,
            timeline TEXT,
            club_url TEXT,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'new',
            source TEXT NOT NULL DEFAULT 'contact_form',
            user_agent TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_onboarding_requests_created_at "
        "ON club_onboarding_requests (created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS club_onboarding_requests")
