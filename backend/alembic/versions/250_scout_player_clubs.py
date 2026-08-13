"""BetterScout — multi-club player tracking + player search history

A tracked player (ScoutedPlayer) could only ever hold ONE club's stats —
adding the same person from a second club silently overwrote the first
club's data instead of combining it (Spencer Green plays several clubs;
BetterScout could only ever remember the last one added). scouted_player_clubs
is the child table that fixes this: one row per linked club-stint, with
exactly one marked is_primary — ScoutedPlayer.club_org_guid/club_name/
stats_payload/stats_built_at stay as-is and become a mirror of whichever row
is primary, so every existing reader of those columns keeps working
unchanged. See services/scout_discovery.py for the linking logic and
services/scout_feed.py for the name-based cross-club matching that proposes
candidates (there is no participant-GUID-across-clubs API to look this up
directly — confirmed unreachable against PlayHQ/Pulselive's own endpoints).

scout_player_search_views is the player-viewing-history mirror of the
existing scout_club_views (see 244_scout_club_views.py) — a per-org record
of which players an org has looked at, upserted on profile view.

Revision ID: 250
Revises: 249
"""
from alembic import op

revision = "250"
down_revision = "249"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scouted_player_clubs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            club_org_guid TEXT NOT NULL,
            club_name TEXT,
            grade_name TEXT,
            grassroots_participant_id TEXT,
            is_primary BOOLEAN NOT NULL DEFAULT false,
            stats_payload JSONB,
            stats_built_at TIMESTAMPTZ,
            linked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            linked_via TEXT NOT NULL DEFAULT 'add',
            CONSTRAINT uq_scouted_player_clubs_player_club UNIQUE (scouted_player_id, club_org_guid)
        )
    """)
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_scouted_player_clubs_primary "
        "ON scouted_player_clubs(scouted_player_id) WHERE is_primary"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scouted_player_clubs_player "
        "ON scouted_player_clubs(scouted_player_id)"
    )

    # Backfill: every existing single-club ScoutedPlayer becomes its own
    # primary row, carrying its existing stats forward unchanged.
    op.execute("""
        INSERT INTO scouted_player_clubs
            (id, scouted_player_id, club_org_guid, club_name, grassroots_participant_id,
             stats_payload, stats_built_at, is_primary, linked_via)
        SELECT gen_random_uuid(), id, club_org_guid, club_name, grassroots_participant_id,
               stats_payload, stats_built_at, true, 'add'
        FROM scouted_players
        WHERE club_org_guid IS NOT NULL
        ON CONFLICT (scouted_player_id, club_org_guid) DO NOTHING
    """)

    op.execute("ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS other_club_candidates JSONB")
    op.execute("ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS other_club_candidates_checked_at TIMESTAMPTZ")

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_player_search_views (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            scouted_player_id UUID NOT NULL REFERENCES scouted_players(id) ON DELETE CASCADE,
            player_name TEXT,
            query_text TEXT,
            last_viewed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_scout_player_search_views_org_player UNIQUE (scout_org_id, scouted_player_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_player_search_views_org "
        "ON scout_player_search_views(scout_org_id, last_viewed_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_player_search_views")
    op.execute("ALTER TABLE scouted_players DROP COLUMN IF EXISTS other_club_candidates_checked_at")
    op.execute("ALTER TABLE scouted_players DROP COLUMN IF EXISTS other_club_candidates")
    op.execute("DROP TABLE IF EXISTS scouted_player_clubs")
