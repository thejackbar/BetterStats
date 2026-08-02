"""BetterClubManager Directory — non-player people + third parties.

Adds two columns to the shared person spine `fee_members` so ClubManager can own
its own people:
    member_category — a light tag (volunteer / parent / committee / life_member /
                      third_party / official / other) driving the Directory
                      filters. A linked player is a "Player" implicitly; this is
                      for the non-player kinds.
    archived_at     — reversible archive (ClubManager hides archived people from
                      the Directory; a NULL means active).

Mirrored idempotently in app/main.py lifespan (migration 212 block).
"""
from alembic import op

revision = "212"
down_revision = "211"
branch_labels = None
depends_on = None

STATEMENTS = [
    "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS member_category TEXT",
    "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ",
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS member_category")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS archived_at")
