"""BetterScout — scout_shared_comparisons (Compare's read-only share link)

A read-only public link onto a snapshot of 2-5 scouted_players ids — its
own token/table rather than reusing ScoutWatchlistCard.share_token, since a
comparison names several players at once. See models/scout.py's
ScoutSharedComparison docstring for why `expires_at` is stamped once at
creation rather than checked dynamically against the org's live setting.

Revision ID: 246
Revises: 245
"""
from alembic import op

revision = "246"
down_revision = "245"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_shared_comparisons (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            player_ids JSONB NOT NULL,
            token TEXT NOT NULL UNIQUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            expires_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_shared_comparisons_org "
        "ON scout_shared_comparisons(scout_org_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_shared_comparisons")
