"""Games — per-side organisation id for shared match rows

A CA match between two clubs that both sync with BetterCricket shares ONE
`games.id` row (the raw match GUID) — whichever club's sync discovered it
first created the row, with `grade_id` pointing at ITS OWN grade and
`opp_org_id`/`opp_club_name` set from ITS OWN perspective only (a single pair
of columns can't hold both clubs' perspectives on the same row, and the
UPDATE that sets them is guarded `WHERE opp_org_id IS NULL`, so the second
club's sync can never correct it). Two symptoms, same root cause:
  - the second club's genuine wins/losses go missing from their own Games
    list — it's org-scoped via grade_id -> season -> organisation_id, and a
    shared row's grade_id belongs to whichever club synced it first
  - a player's "stats by opposition" can show their OWN club as the
    opponent — opp_org_id was stamped from the OTHER club's perspective

Adds `home_org_id` / `away_org_id` (nullable) — one column per side, so each
synced club can independently record which side of the match it was on
without clobbering the other club's write, unlike the single-value
opp_org_id/opp_club_name (left untouched, still the fallback for a genuinely
unsynced opponent). Populated at sync time (see sync.py); a backfill script
(app/scripts/backfill_game_org_ids.py) derives them for already-synced games
from existing game_appearances without waiting on a re-sync.

Revision ID: 167
Revises: 166
Create Date: 2026-07-21
"""
from alembic import op


revision = '167'
down_revision = '166'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS home_org_id UUID")
    op.execute("ALTER TABLE games ADD COLUMN IF NOT EXISTS away_org_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS idx_games_home_org_id ON games(home_org_id) WHERE home_org_id IS NOT NULL")
    op.execute("CREATE INDEX IF NOT EXISTS idx_games_away_org_id ON games(away_org_id) WHERE away_org_id IS NOT NULL")

    # v_effective_games must carry the two new columns too — CREATE OR REPLACE
    # VIEW can only append columns at the end, not reorder/remove existing
    # ones, since every consumer already reads through this view, not the
    # bare table.
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_games AS
        SELECT
            id, grade_id, played_at, home_team, away_team,
            home_club, away_club, opp_org_id, opp_club_name,
            result, winning_team, is_final,
            raw_payload, venue, match_format,
            'api'::text AS source,
            home_org_id, away_org_id
        FROM games
        UNION ALL
        SELECT
            id, grade_id, played_at, home_team, away_team,
            NULL::text AS home_club,
            NULL::text AS away_club,
            NULL::text AS opp_org_id,
            opposition AS opp_club_name,
            result, winning_team, is_final,
            NULL::jsonb AS raw_payload,
            venue, match_format,
            'manual'::text AS source,
            NULL::uuid AS home_org_id,
            NULL::uuid AS away_org_id
        FROM manual_games
    """)


def downgrade() -> None:
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_games AS
        SELECT
            id, grade_id, played_at, home_team, away_team,
            home_club, away_club, opp_org_id, opp_club_name,
            result, winning_team, is_final,
            raw_payload, venue, match_format,
            'api'::text AS source
        FROM games
        UNION ALL
        SELECT
            id, grade_id, played_at, home_team, away_team,
            NULL::text AS home_club,
            NULL::text AS away_club,
            NULL::text AS opp_org_id,
            opposition AS opp_club_name,
            result, winning_team, is_final,
            NULL::jsonb AS raw_payload,
            venue, match_format,
            'manual'::text AS source
        FROM manual_games
    """)
    op.execute("DROP INDEX IF EXISTS idx_games_away_org_id")
    op.execute("DROP INDEX IF EXISTS idx_games_home_org_id")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS away_org_id")
    op.execute("ALTER TABLE games DROP COLUMN IF EXISTS home_org_id")
