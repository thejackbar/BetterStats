"""BetterScout — player discovery: club cache + scouted players + tracking

Three tables, none with any foreign key to organisations/players/club data —
BetterScout's isolation from club data is structural, not just conventional.
See models/scout.py for the full rationale on each table.

- scout_club_cache: platform-wide cache of one AU club's roster+career build
  (services.iq_scout._build_career's output), shared across every Scout Org
  that browses that club. Mirrors opposition_dossiers' build/poll shape but
  keyed on the club's own CA GUID instead of an organisation_id.
- scouted_players: the durable per-person record, created only when a scout
  explicitly adds someone. stats_payload is a snapshot, not live-recomputed.
- scout_tracked_players: the minimal per-tenant join ("this Scout Org added
  this player") — deliberately not the full watchlist, which is a later
  phase extending this same join rather than replacing it.

Revision ID: 237
Revises: 236
"""
from alembic import op

revision = "237"
down_revision = "236"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_club_cache (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            club_org_guid TEXT NOT NULL UNIQUE,
            club_name TEXT,
            status TEXT NOT NULL DEFAULT 'building',
            payload JSONB,
            error TEXT,
            built_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS scouted_players (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            source TEXT NOT NULL,
            grassroots_participant_id TEXT,
            club_org_guid TEXT,
            club_name TEXT,
            name TEXT NOT NULL,
            grade_name TEXT,
            notes TEXT,
            stats_payload JSONB,
            stats_built_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scouted_players_participant UNIQUE (grassroots_participant_id)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_tracked_players (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_tracked_player UNIQUE (scout_org_id, scouted_player_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_tracked_players_org "
        "ON scout_tracked_players(scout_org_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_tracked_players")
    op.execute("DROP TABLE IF EXISTS scouted_players")
    op.execute("DROP TABLE IF EXISTS scout_club_cache")
