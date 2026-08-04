"""Role-type categories + committee office-bearer flag.

- club_role_types.category — classifies a role type as
  committee / volunteer / paid / third_party / other, so the Roles surfaces can
  show only non-committee role types and committee positions only committee ones.
  Defaults to 'volunteer' (non-committee), so nothing existing is hidden until a
  club deliberately marks a type 'committee'.
- committee_positions.is_office_bearer — marks the executive/legal office bearers
  (President, Vice President, Treasurer, Secretary) apart from general elected
  committee members.

Mirrored idempotently in app/main.py lifespan (migration 213 block).
"""
from alembic import op

revision = "213"
down_revision = "212"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE club_role_types ADD COLUMN IF NOT EXISTS category TEXT NOT NULL DEFAULT 'volunteer'",
    "ALTER TABLE committee_positions ADD COLUMN IF NOT EXISTS is_office_bearer BOOLEAN NOT NULL DEFAULT FALSE",
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    op.execute("ALTER TABLE club_role_types DROP COLUMN IF EXISTS category")
    op.execute("ALTER TABLE committee_positions DROP COLUMN IF EXISTS is_office_bearer")
