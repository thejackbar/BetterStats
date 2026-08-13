"""BetterScout — player profile: notes timeline + photo

scout_player_notes is the dated scouting log ("14 Feb 2026 · Dan Wilson ·
Watched live") behind the profile's Scouting notes card. photo_url/
photo_data/photo_mime on scouted_players is the scout-uploaded fallback —
a player already linked via services/scout_internal_link.py reads their
real BetterCricket player photo first (see scout_discovery.player_out); this
is what's used when there's no internal link, or that player has no photo
either.

Revision ID: 243
Revises: 242
"""
from alembic import op

revision = "243"
down_revision = "242"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in [
        "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_url TEXT",
        "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_data BYTEA",
        "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS photo_mime TEXT",
    ]:
        op.execute(stmt)

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_player_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            author_scout_user_id UUID REFERENCES scout_users(id) ON DELETE SET NULL,
            body TEXT NOT NULL,
            kind TEXT NOT NULL DEFAULT 'other',
            occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_player_notes_org_player "
        "ON scout_player_notes(scout_org_id, scouted_player_id, occurred_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_player_notes")
    for stmt in [
        "ALTER TABLE scouted_players DROP COLUMN IF EXISTS photo_mime",
        "ALTER TABLE scouted_players DROP COLUMN IF EXISTS photo_data",
        "ALTER TABLE scouted_players DROP COLUMN IF EXISTS photo_url",
    ]:
        op.execute(stmt)
