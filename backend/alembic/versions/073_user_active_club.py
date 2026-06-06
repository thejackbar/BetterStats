"""Super-admin club switching: users.active_club_id.

Adds a nullable ``active_club_id`` to ``users`` so a super admin (Better staff)
can "act as" any club — every club-scoped request resolves to this club instead
of their single home-membership club. NULL means "act as the home club".

ON DELETE SET NULL so removing a club never strands a staff account on a
dangling reference. Additive + idempotent; non-super accounts ignore the column
entirely (see ``auth._effective_club_id``), so nothing changes for them.

Revision ID: 073
Revises: 072
Create Date: 2026-06-06

"""
from alembic import op


revision = '073'
down_revision = '072'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS active_club_id UUID "
        "REFERENCES organisations(id) ON DELETE SET NULL"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS active_club_id")
