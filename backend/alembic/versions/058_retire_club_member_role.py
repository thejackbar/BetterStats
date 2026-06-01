"""retire club_member role: promote existing members to club_admin

The club_member role (capability-restricted member logins) is retired — the
product is admin-only (super_admin / club_admin), matching the ecosystem
master plan's "admin-only, no member logins" decision. Promote every existing
club_member membership to club_admin so those users regain full access.

Capabilities rows are left as-is but ignored (club_admin implies all caps).

Revision ID: 058
Revises: 057
Create Date: 2026-06-01

"""
from alembic import op


revision = '058'
down_revision = '057'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE club_memberships SET role = 'club_admin' WHERE role = 'club_member'")


def downgrade() -> None:
    # Irreversible — we can't tell which admins were previously members.
    pass
