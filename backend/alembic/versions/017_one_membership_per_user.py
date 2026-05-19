"""Limit each admin account to a single club membership

The app already assumes one ClubMembership per user (login, get_current_club
and require_super_admin all read a single row), but nothing enforced it. Add
a unique constraint on club_memberships.user_id so an admin account is linked
to exactly one club.

Any pre-existing duplicate memberships are collapsed first — keeping the
super_admin row if there is one, otherwise the oldest.

Revision ID: 017
Revises: 016
Create Date: 2026-05-19
"""
import sqlalchemy as sa
from alembic import op

revision = '017'
down_revision = '016'
branch_labels = None
depends_on = None


def upgrade():
    conn = op.get_bind()
    # Defensive de-dupe (a no-op when there are no duplicates).
    conn.execute(sa.text("""
        DELETE FROM club_memberships cm
        WHERE cm.id <> (
            SELECT keep.id FROM club_memberships keep
            WHERE keep.user_id = cm.user_id
            ORDER BY (keep.role = 'super_admin') DESC, keep.created_at ASC
            LIMIT 1
        )
    """))
    op.create_unique_constraint('uq_membership_one_per_user', 'club_memberships', ['user_id'])


def downgrade():
    op.drop_constraint('uq_membership_one_per_user', 'club_memberships', type_='unique')
