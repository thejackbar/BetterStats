"""BetterScout — scout_milestone_seen (Milestones "Mark as seen" + badge)

One row per (org, player, milestone) dismissed on the Reached table.
Existence is the only signal there is; services/scout_milestones.py counts
reached rows with no matching row here for the sidebar badge and the
"N since your last visit" count.

Revision ID: 245
Revises: 244
"""
from alembic import op

revision = "245"
down_revision = "244"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_milestone_seen (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            milestone_type TEXT NOT NULL,
            milestone_value INTEGER NOT NULL,
            seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_milestone_seen UNIQUE (scout_org_id, scouted_player_id, milestone_type, milestone_value)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_milestone_seen_org "
        "ON scout_milestone_seen(scout_org_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_milestone_seen")
