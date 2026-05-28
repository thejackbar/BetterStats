"""Add manual_career_adjustments into v_effective_player_season_stats.

When the manual entry feature shipped in PR 1, career adjustments got
their own table but the player_season_stats view never UNIONed them in
— so they did nothing. Career rows are represented with NULL season_id
so they're invisible to season-keyed leaderboards (correct) but show
up in player-profile career views (where queries don't filter by
season).

Revision ID: 039
Revises: 038
Create Date: 2026-05-27
"""
from alembic import op


revision = '039'
down_revision = '038'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop + recreate (CREATE OR REPLACE doesn't allow adding columns to a
    # view in PostgreSQL, but our column list is unchanged so we could've
    # used it — keeping DROP/CREATE to be safe against future column shape
    # drift).
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute("""
        CREATE VIEW v_effective_player_season_stats AS
        SELECT
            player_id, season_id,
            NULL::uuid AS grade_id,
            'api'::text AS source,
            matches, batting_innings, runs, not_outs, balls_faced,
            fifties, hundreds, ducks,
            high_score, is_hs_not_out, batting_average, batting_strike_rate,
            fours, sixes, batting_minutes,
            bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
            bowling_economy, bowling_average, bowling_strike_rate,
            best_bowling_wickets, best_bowling_figures, five_wicket_innings,
            wides, no_balls,
            catches, catches_wk, catches_non_wk, run_outs,
            assisted_run_outs, unassisted_run_outs, stumpings
        FROM player_season_stats

        UNION ALL

        SELECT
            player_id, season_id, grade_id,
            'manual_aggregate'::text AS source,
            games_played AS matches,
            batting_innings,
            batting_runs AS runs,
            batting_not_outs AS not_outs,
            batting_balls AS balls_faced,
            batting_fifties AS fifties,
            batting_hundreds AS hundreds,
            batting_ducks AS ducks,
            batting_high_score AS high_score,
            batting_high_score_not_out AS is_hs_not_out,
            NULL::numeric AS batting_average,
            NULL::numeric AS batting_strike_rate,
            batting_fours AS fours,
            batting_sixes AS sixes,
            NULL::integer AS batting_minutes,
            bowling_innings,
            bowling_wickets AS wickets,
            bowling_overs AS overs,
            bowling_balls,
            bowling_runs AS runs_conceded,
            bowling_maidens AS maidens,
            NULL::numeric AS bowling_economy,
            NULL::numeric AS bowling_average,
            NULL::numeric AS bowling_strike_rate,
            bowling_best_wickets AS best_bowling_wickets,
            bowling_best_figures AS best_bowling_figures,
            bowling_five_wicket_innings AS five_wicket_innings,
            bowling_wides AS wides,
            bowling_no_balls AS no_balls,
            fielding_catches AS catches,
            fielding_catches_wk AS catches_wk,
            GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
            fielding_run_outs AS run_outs,
            0 AS assisted_run_outs,
            fielding_run_outs AS unassisted_run_outs,
            fielding_stumpings AS stumpings
        FROM manual_season_adjustments

        UNION ALL

        -- Career-only adjustments (NULL season_id so they're invisible
        -- to season-keyed leaderboards but flow into career profile views).
        SELECT
            player_id,
            NULL::uuid AS season_id,
            NULL::uuid AS grade_id,
            'manual_career'::text AS source,
            games_played AS matches,
            batting_innings,
            batting_runs AS runs,
            batting_not_outs AS not_outs,
            batting_balls AS balls_faced,
            batting_fifties AS fifties,
            batting_hundreds AS hundreds,
            batting_ducks AS ducks,
            batting_high_score AS high_score,
            batting_high_score_not_out AS is_hs_not_out,
            NULL::numeric AS batting_average,
            NULL::numeric AS batting_strike_rate,
            batting_fours AS fours,
            batting_sixes AS sixes,
            NULL::integer AS batting_minutes,
            bowling_innings,
            bowling_wickets AS wickets,
            bowling_overs AS overs,
            bowling_balls,
            bowling_runs AS runs_conceded,
            bowling_maidens AS maidens,
            NULL::numeric AS bowling_economy,
            NULL::numeric AS bowling_average,
            NULL::numeric AS bowling_strike_rate,
            bowling_best_wickets AS best_bowling_wickets,
            bowling_best_figures AS best_bowling_figures,
            bowling_five_wicket_innings AS five_wicket_innings,
            0 AS wides,
            0 AS no_balls,
            fielding_catches AS catches,
            fielding_catches_wk AS catches_wk,
            GREATEST(fielding_catches - fielding_catches_wk, 0) AS catches_non_wk,
            fielding_run_outs AS run_outs,
            0 AS assisted_run_outs,
            fielding_run_outs AS unassisted_run_outs,
            fielding_stumpings AS stumpings
        FROM manual_career_adjustments

        UNION ALL

        -- Manual games rolled up per (player, season, grade) — unchanged
        -- from migration 037.
        SELECT
            mg_agg.player_id,
            mg_agg.season_id,
            mg_agg.grade_id,
            'manual_game'::text AS source,
            mg_agg.matches,
            mg_agg.batting_innings,
            mg_agg.runs,
            mg_agg.not_outs,
            mg_agg.balls_faced,
            mg_agg.fifties,
            mg_agg.hundreds,
            mg_agg.ducks,
            mg_agg.high_score,
            mg_agg.is_hs_not_out,
            NULL::numeric AS batting_average,
            NULL::numeric AS batting_strike_rate,
            mg_agg.fours,
            mg_agg.sixes,
            NULL::integer AS batting_minutes,
            mg_agg.bowling_innings,
            mg_agg.wickets,
            mg_agg.overs,
            mg_agg.bowling_balls,
            mg_agg.runs_conceded,
            mg_agg.maidens,
            NULL::numeric AS bowling_economy,
            NULL::numeric AS bowling_average,
            NULL::numeric AS bowling_strike_rate,
            mg_agg.best_bowling_wickets,
            mg_agg.best_bowling_figures,
            mg_agg.five_wicket_innings,
            mg_agg.wides,
            mg_agg.no_balls,
            mg_agg.catches,
            mg_agg.catches_wk,
            GREATEST(mg_agg.catches - mg_agg.catches_wk, 0) AS catches_non_wk,
            mg_agg.run_outs,
            0 AS assisted_run_outs,
            mg_agg.run_outs AS unassisted_run_outs,
            mg_agg.stumpings
        FROM (
            WITH player_games AS (
                SELECT mg.id AS manual_game_id, mg.season_id, mg.grade_id, mbi.player_id
                FROM manual_games mg JOIN manual_batting_innings mbi ON mbi.manual_game_id = mg.id
                UNION
                SELECT mg.id, mg.season_id, mg.grade_id, mbs.player_id
                FROM manual_games mg JOIN manual_bowling_spells mbs ON mbs.manual_game_id = mg.id
                UNION
                SELECT mg.id, mg.season_id, mg.grade_id, mfs.player_id
                FROM manual_games mg JOIN manual_fielding_stats mfs ON mfs.manual_game_id = mg.id
            )
            SELECT
                pg.player_id,
                pg.season_id,
                pg.grade_id,
                COUNT(DISTINCT pg.manual_game_id)::integer AS matches,
                COUNT(*) FILTER (WHERE mbi.id IS NOT NULL AND NOT mbi.did_not_bat)::integer AS batting_innings,
                COALESCE(SUM(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS runs,
                COUNT(*) FILTER (WHERE mbi.not_out)::integer AS not_outs,
                COALESCE(SUM(mbi.balls) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS balls_faced,
                COUNT(*) FILTER (WHERE mbi.runs >= 50 AND mbi.runs < 100)::integer AS fifties,
                COUNT(*) FILTER (WHERE mbi.runs >= 100)::integer AS hundreds,
                COUNT(*) FILTER (WHERE mbi.runs = 0 AND NOT mbi.not_out AND NOT mbi.did_not_bat)::integer AS ducks,
                MAX(mbi.runs) FILTER (WHERE NOT mbi.did_not_bat) AS high_score,
                COALESCE(BOOL_OR(mbi.not_out) FILTER (
                    WHERE mbi.runs = (
                        SELECT MAX(mbi2.runs)
                        FROM manual_batting_innings mbi2
                        JOIN manual_games mg2 ON mg2.id = mbi2.manual_game_id
                        WHERE mbi2.player_id = pg.player_id
                          AND mg2.season_id = pg.season_id
                          AND COALESCE(mg2.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                              = COALESCE(pg.grade_id, '00000000-0000-0000-0000-000000000000'::uuid)
                          AND NOT mbi2.did_not_bat
                    )
                ), false) AS is_hs_not_out,
                COALESCE(SUM(mbi.fours) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS fours,
                COALESCE(SUM(mbi.sixes) FILTER (WHERE NOT mbi.did_not_bat), 0)::integer AS sixes,
                COUNT(*) FILTER (WHERE mbs.id IS NOT NULL)::integer AS bowling_innings,
                COALESCE(SUM(mbs.wickets), 0)::integer AS wickets,
                COALESCE(SUM(mbs.overs), 0)::numeric AS overs,
                COALESCE(SUM(FLOOR(mbs.overs)::integer * 6
                             + ((mbs.overs - FLOOR(mbs.overs)) * 10)::integer), 0)::integer AS bowling_balls,
                COALESCE(SUM(mbs.runs), 0)::integer AS runs_conceded,
                COALESCE(SUM(mbs.maidens), 0)::integer AS maidens,
                MAX(mbs.wickets) AS best_bowling_wickets,
                NULL::text AS best_bowling_figures,
                COUNT(*) FILTER (WHERE mbs.wickets >= 5)::integer AS five_wicket_innings,
                COALESCE(SUM(mbs.wides), 0)::integer AS wides,
                COALESCE(SUM(mbs.no_balls), 0)::integer AS no_balls,
                COALESCE(SUM(mfs.catches), 0)::integer AS catches,
                COALESCE(SUM(mfs.catches_wk), 0)::integer AS catches_wk,
                COALESCE(SUM(mfs.run_outs), 0)::integer AS run_outs,
                COALESCE(SUM(mfs.stumpings), 0)::integer AS stumpings
            FROM player_games pg
            LEFT JOIN manual_batting_innings mbi
                ON mbi.manual_game_id = pg.manual_game_id AND mbi.player_id = pg.player_id
            LEFT JOIN manual_bowling_spells mbs
                ON mbs.manual_game_id = pg.manual_game_id AND mbs.player_id = pg.player_id
            LEFT JOIN manual_fielding_stats mfs
                ON mfs.manual_game_id = pg.manual_game_id AND mfs.player_id = pg.player_id
            GROUP BY pg.player_id, pg.season_id, pg.grade_id
        ) mg_agg
    """)


def downgrade() -> None:
    # Restore the 037-era view without manual_career_adjustments.
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute("""
        CREATE VIEW v_effective_player_season_stats AS
        SELECT
            player_id, season_id,
            NULL::uuid AS grade_id,
            'api'::text AS source,
            matches, batting_innings, runs, not_outs, balls_faced,
            fifties, hundreds, ducks,
            high_score, is_hs_not_out, batting_average, batting_strike_rate,
            fours, sixes, batting_minutes,
            bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
            bowling_economy, bowling_average, bowling_strike_rate,
            best_bowling_wickets, best_bowling_figures, five_wicket_innings,
            wides, no_balls,
            catches, catches_wk, catches_non_wk, run_outs,
            assisted_run_outs, unassisted_run_outs, stumpings
        FROM player_season_stats
    """)
