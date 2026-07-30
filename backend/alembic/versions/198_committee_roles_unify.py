"""Unify committee positions with the Roles catalogue.

A committee position is now a committee-flagged club_role. club_roles gains
``is_committee``; committee_positions gains ``role_id`` linking each position
to its role (the position row stays the anchor for term/task/document/AGM FKs,
its name/responsibilities kept in sync from the role). Non-destructive: two
nullable/defaulted columns only, no data moved.

Mirrored idempotently in app/main.py lifespan (migration 198 block).
"""
from alembic import op

revision = "198"
down_revision = "197"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("ALTER TABLE club_roles ADD COLUMN IF NOT EXISTS is_committee BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE committee_positions ADD COLUMN IF NOT EXISTS role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL")


def downgrade():
    op.execute("ALTER TABLE committee_positions DROP COLUMN IF EXISTS role_id")
    op.execute("ALTER TABLE club_roles DROP COLUMN IF EXISTS is_committee")
