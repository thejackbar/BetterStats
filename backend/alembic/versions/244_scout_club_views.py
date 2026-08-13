"""BetterScout — scout_club_views (Overview's "Clubs you've looked at")

ScoutClubCache is platform-wide (one build per club, shared by every Scout
Org — see its own docstring), so it can't answer "which clubs has THIS org
looked at". This table is the per-org viewing history, upserted whenever an
org fetches a club's roster.

Revision ID: 244
Revises: 243
"""
from alembic import op

revision = "244"
down_revision = "243"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_club_views (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            club_org_guid TEXT NOT NULL,
            club_name TEXT,
            last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_club_views_org_club UNIQUE (scout_org_id, club_org_guid)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_club_views_org "
        "ON scout_club_views(scout_org_id, last_viewed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_club_views")
