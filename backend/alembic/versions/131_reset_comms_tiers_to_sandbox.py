"""Reset every club's BetterComms tier back to sandbox (again)

Migration 129 already reset production → sandbox, but a boot-time statement in
the app lifespan was still re-promoting every sandbox club to production on each
restart (the comment claimed it had been removed; the actual UPDATE line had
not). That line is now removed, so this one-time reset corrects the clubs the
buggy line re-promoted in the meantime. Every club is sandbox and earns
production only via a super-admin approval.

Suspended clubs stay suspended; the marketing-outreach org is uncapped
regardless of tier so it is left as-is.

Revision ID: 131
Revises: 130
"""
from alembic import op

revision = "131"
down_revision = "130"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE organisations SET comms_tier = 'sandbox' "
               "WHERE comms_tier = 'production' "
               "AND COALESCE(is_marketing_outreach, false) = false")


def downgrade() -> None:
    pass
