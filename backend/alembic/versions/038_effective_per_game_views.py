"""Effective views for per-game tables so manual data flows into per-innings
queries (records, per-grade leaderboards, fixture lists, player profile
game tables).

Mirrors the v_effective_player_season_stats pattern from migration 037:
each view UNION-ALLs the synced table with its manual counterpart,
carrying a `source` discriminator ('api' | 'manual') for admin tooling.

Existing per-game read paths swap `FROM batting_innings` → `FROM
v_effective_batting_innings`, etc. Write paths (sync, hard-refresh,
admin merges) keep pointing at the raw tables.

Revision ID: 038
Revises: 037
Create Date: 2026-05-27
"""
from alembic import op


revision = '038'
down_revision = '037'
branch_labels = None
depends_on = None


def upgrade() -> None:
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

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_batting_innings AS
        SELECT
            id, game_id, player_id, innings_number,
            runs, balls, fours, sixes, strike_rate,
            dismissal_type, not_out, batting_position, did_not_bat,
            'api'::text AS source
        FROM batting_innings
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, player_id, innings_number,
            runs, balls, fours, sixes, strike_rate,
            dismissal_type, not_out, batting_position, did_not_bat,
            'manual'::text AS source
        FROM manual_batting_innings
    """)

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_bowling_spells AS
        SELECT
            id, game_id, player_id, innings_number,
            overs, maidens, runs, wickets, wides, no_balls, economy,
            'api'::text AS source
        FROM bowling_spells
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, player_id, innings_number,
            overs, maidens, runs, wickets, wides, no_balls, economy,
            'manual'::text AS source
        FROM manual_bowling_spells
    """)

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_fielding_stats AS
        SELECT
            id, game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'api'::text AS source
        FROM fielding_stats
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, player_id,
            catches, catches_wk, run_outs, stumpings,
            'manual'::text AS source
        FROM manual_fielding_stats
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_effective_fielding_stats")
    op.execute("DROP VIEW IF EXISTS v_effective_bowling_spells")
    op.execute("DROP VIEW IF EXISTS v_effective_batting_innings")
    op.execute("DROP VIEW IF EXISTS v_effective_games")
