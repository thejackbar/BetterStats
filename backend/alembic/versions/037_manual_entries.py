"""Manual entry tables for historical stats.

Adds seven tables that let club admins enter historical/missing data:

- manual_games (+ manual_batting_innings, manual_bowling_spells,
  manual_fielding_stats): full or partial scorecard rows that survive
  every sync because nothing else writes here.
- manual_season_adjustments: per-player-per-season aggregate deltas for
  when only totals are available (no per-game detail).
- manual_career_adjustments: per-player career deltas for the case
  where season info isn't available at all.
- manual_edit_logs: append-only audit trail with the merge_logs.undone_at
  soft-delete pattern, so every CREATE/UPDATE/DELETE is reversible.

Also creates v_effective_player_season_stats: a UNION ALL view that
existing aggregate-leaderboard / career queries can read from instead of
player_season_stats directly. Each row carries a `source` column
('api' | 'manual_aggregate' | 'manual_game') so admin views can distinguish
provenance; the public UI just ignores it.

Revision ID: 037
Revises: 036
Create Date: 2026-05-27
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '037'
down_revision = '036'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── manual_games ─────────────────────────────────────────────────────────
    op.create_table(
        "manual_games",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade_id", UUID(as_uuid=True), sa.ForeignKey("grades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("played_at", sa.Date(), nullable=True),
        sa.Column("home_team", sa.Text(), nullable=True),
        sa.Column("away_team", sa.Text(), nullable=True),
        sa.Column("opposition", sa.Text(), nullable=True),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("winning_team", sa.Text(), nullable=True),
        sa.Column("is_final", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("match_format", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_manual_games_org", "manual_games", ["organisation_id"])
    op.create_index("ix_manual_games_season", "manual_games", ["season_id"])

    # ─── manual_batting_innings ──────────────────────────────────────────────
    op.create_table(
        "manual_batting_innings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("manual_game_id", UUID(as_uuid=True), sa.ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("batting_position", sa.Integer(), nullable=True),
        sa.Column("runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("balls", sa.Integer(), nullable=True),
        sa.Column("fours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("sixes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("strike_rate", sa.Numeric(6, 2), nullable=True),
        sa.Column("dismissal_type", sa.Text(), nullable=True),
        sa.Column("not_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("did_not_bat", sa.Boolean(), server_default="false", nullable=False),
        sa.UniqueConstraint("manual_game_id", "innings_number", "player_id", name="uq_manual_batting_game_inns_player"),
    )
    op.create_index("ix_manual_batting_player", "manual_batting_innings", ["player_id"])

    # ─── manual_bowling_spells ───────────────────────────────────────────────
    op.create_table(
        "manual_bowling_spells",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("manual_game_id", UUID(as_uuid=True), sa.ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("innings_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("overs", sa.Numeric(4, 1), nullable=True),
        sa.Column("maidens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wickets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("wides", sa.Integer(), server_default="0", nullable=False),
        sa.Column("no_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("economy", sa.Numeric(5, 2), nullable=True),
    )
    op.create_index("ix_manual_bowling_player", "manual_bowling_spells", ["player_id"])

    # ─── manual_fielding_stats ───────────────────────────────────────────────
    op.create_table(
        "manual_fielding_stats",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("manual_game_id", UUID(as_uuid=True), sa.ForeignKey("manual_games.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("catches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("catches_wk", sa.Integer(), server_default="0", nullable=False),
        sa.Column("run_outs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("stumpings", sa.Integer(), server_default="0", nullable=False),
        sa.UniqueConstraint("manual_game_id", "player_id", name="uq_manual_fielding_game_player"),
    )
    op.create_index("ix_manual_fielding_player", "manual_fielding_stats", ["player_id"])

    # ─── manual_season_adjustments ───────────────────────────────────────────
    op.create_table(
        "manual_season_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade_id", UUID(as_uuid=True), sa.ForeignKey("grades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("games_played", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_not_outs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_fours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_sixes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_fifties", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_hundreds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_ducks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_high_score", sa.Integer(), nullable=True),
        sa.Column("batting_high_score_not_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("bowling_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_overs", sa.Numeric(8, 1), server_default="0", nullable=False),
        sa.Column("bowling_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_maidens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_wickets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_wides", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_no_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_five_wicket_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_best_wickets", sa.Integer(), nullable=True),
        sa.Column("bowling_best_figures", sa.Text(), nullable=True),
        sa.Column("fielding_catches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_catches_wk", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_run_outs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_stumpings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("player_id", "season_id", "grade_id", name="uq_manual_season_adj_player_season_grade"),
    )
    op.create_index("ix_manual_season_adj_org", "manual_season_adjustments", ["organisation_id"])
    op.create_index("ix_manual_season_adj_player", "manual_season_adjustments", ["player_id"])

    # ─── manual_career_adjustments ───────────────────────────────────────────
    op.create_table(
        "manual_career_adjustments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("games_played", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_not_outs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_fours", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_sixes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_fifties", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_hundreds", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_ducks", sa.Integer(), server_default="0", nullable=False),
        sa.Column("batting_high_score", sa.Integer(), nullable=True),
        sa.Column("batting_high_score_not_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("bowling_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_overs", sa.Numeric(8, 1), server_default="0", nullable=False),
        sa.Column("bowling_balls", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_maidens", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_runs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_wickets", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_five_wicket_innings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("bowling_best_wickets", sa.Integer(), nullable=True),
        sa.Column("bowling_best_figures", sa.Text(), nullable=True),
        sa.Column("fielding_catches", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_catches_wk", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_run_outs", sa.Integer(), server_default="0", nullable=False),
        sa.Column("fielding_stumpings", sa.Integer(), server_default="0", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("player_id", "organisation_id", name="uq_manual_career_adj_player_org"),
    )
    op.create_index("ix_manual_career_adj_org", "manual_career_adjustments", ["organisation_id"])
    op.create_index("ix_manual_career_adj_player", "manual_career_adjustments", ["player_id"])

    # ─── manual_edit_logs (mirrors merge_logs.undone_at pattern) ─────────────
    op.create_table(
        "manual_edit_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("target_table", sa.Text(), nullable=False),
        sa.Column("target_id", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("before_json", JSONB, nullable=True),
        sa.Column("after_json", JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("undone_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("undone_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_manual_edit_log_org_created", "manual_edit_logs", ["organisation_id", "created_at"])

    # ─── v_effective_player_season_stats ─────────────────────────────────────
    # UNION ALL of synced + manual season-aggregates + manual-game rollups.
    # Existing leaderboard / career queries can SELECT FROM this in place of
    # player_season_stats; the only schema change is the extra `source` and
    # `grade_id` columns.
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_player_season_stats AS
        -- API-synced rows
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

        -- Manual season-aggregate adjustments
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

        -- Manual games rolled up per (player, season, grade)
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
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.drop_table("manual_edit_logs")
    op.drop_table("manual_career_adjustments")
    op.drop_table("manual_season_adjustments")
    op.drop_table("manual_fielding_stats")
    op.drop_table("manual_bowling_spells")
    op.drop_table("manual_batting_innings")
    op.drop_table("manual_games")
