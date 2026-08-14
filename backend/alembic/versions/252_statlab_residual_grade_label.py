"""Surface grade_label on v_effective_player_season_stats, for StatLab's residual path.

Reported: a club merged eleven decades-of-different-named grades into one
canonical "VSDCA 1st XI" (Merge Grades), but StatLab's GRADE filter showed
nothing before 2008/09 — the season this club's data switches from bulk-
imported (BetterImport) season/career totals to real per-game scorecards.

Two separate defects, both in ``services/statlab.py``:

  * ``_RESIDUAL_DISQUALIFYING_MATCH_KEYS`` listed ``grade_name`` as a filter a
    residual (no-per-game-data) row "simply cannot be tested against" — untrue,
    and contradicted the block comment directly above it, which already
    claimed grade filters "can still be answered". The moment GRADE was
    filtered, every pre-2008/09 imported row was dropped from
    ``query_player_career``/``query_player_season`` outright.
  * ``query_player_grade`` (one row per player+grade) had no residual branch
    at all, filtered or not — it structurally could never show imported
    history under any grade.

migration 154 already solved the identical problem for leaderboards
(``aggregations.py``'s ``_IMPORT_GRADE_MATCH``), by adding
``import_effective_deltas.grade_label`` — a season-scope import delta has a
real ``grade_id`` (one ``grades`` row for that season), but a career-scope
residual spans many seasons' worth of same-named grades, so it's tagged by
grade *name* instead. That column was never surfaced through
``v_effective_player_season_stats`` (aggregations.py reads
``import_effective_deltas`` directly instead), which is what left StatLab's
residual CTEs — which only ever read the view — with nothing to match a
grade filter against for a career-scope row.

This migration appends ``grade_label`` as the view's new final column (NULL
for every branch except ``import``, which already carries it) — additive
only, and appended at the end so no existing consumer (nothing in this
codebase ``SELECT *``s this view) is affected. ``statlab.py`` is updated in
the same change to read it.

Revision ID: 252
Revises: 251
Create Date: 2026-08-14
"""
from alembic import op


revision = '252'
down_revision = '251'
branch_labels = None
depends_on = None


# ── Identical to migration 070's _VIEW_5_BRANCH, with `grade_label` appended
#    as the new final column on every branch. NULL for every branch except
#    `import`, which already carries a real grade_label column (migration 154).
_VIEW_5_BRANCH_WITH_GRADE_LABEL = """
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
        assisted_run_outs, unassisted_run_outs, stumpings,
        NULL::text AS grade_label
    FROM player_season_stats pss
    -- Only surface a season-stats row when its season belongs to the same
    -- organisation as the player. Filters out cross-club rows that CA's shared
    -- participant GUID lets a second club's sync attach to a player owned by
    -- the first club. NULL-org players are kept (can't be scoped).
    WHERE EXISTS (
        SELECT 1
        FROM players pl
        JOIN seasons s ON s.id = pss.season_id
        WHERE pl.id = pss.player_id
          AND (pl.organisation_id IS NULL OR pl.organisation_id = s.organisation_id)
    )

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
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
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
        fielding_stumpings AS stumpings,
        NULL::text AS grade_label
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
        mg_agg.stumpings,
        NULL::text AS grade_label
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

    UNION ALL

    SELECT
        player_id, season_id,
        grade_id,
        'import'::text AS source,
        matches, batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        fours, sixes,
        NULL::integer AS batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk,
        GREATEST(catches - catches_wk, 0) AS catches_non_wk,
        run_outs,
        0 AS assisted_run_outs,
        run_outs AS unassisted_run_outs,
        stumpings,
        grade_label
    FROM import_effective_deltas
"""

# ── The prior (migration 070) 5-branch view, with no grade_label column —
#    used verbatim on downgrade.
_VIEW_5_BRANCH = """
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
    FROM player_season_stats pss
    WHERE EXISTS (
        SELECT 1
        FROM players pl
        JOIN seasons s ON s.id = pss.season_id
        WHERE pl.id = pss.player_id
          AND (pl.organisation_id IS NULL OR pl.organisation_id = s.organisation_id)
    )

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

    UNION ALL

    SELECT
        player_id, season_id,
        grade_id,
        'import'::text AS source,
        matches, batting_innings, runs, not_outs, balls_faced,
        fifties, hundreds, ducks,
        high_score, is_hs_not_out,
        NULL::numeric AS batting_average,
        NULL::numeric AS batting_strike_rate,
        fours, sixes,
        NULL::integer AS batting_minutes,
        bowling_innings, wickets, overs, bowling_balls, runs_conceded, maidens,
        NULL::numeric AS bowling_economy,
        NULL::numeric AS bowling_average,
        NULL::numeric AS bowling_strike_rate,
        best_bowling_wickets, best_bowling_figures, five_wicket_innings,
        wides, no_balls,
        catches, catches_wk,
        GREATEST(catches - catches_wk, 0) AS catches_non_wk,
        run_outs,
        0 AS assisted_run_outs,
        run_outs AS unassisted_run_outs,
        stumpings
    FROM import_effective_deltas
"""


def upgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute(_VIEW_5_BRANCH_WITH_GRADE_LABEL)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute(_VIEW_5_BRANCH)
