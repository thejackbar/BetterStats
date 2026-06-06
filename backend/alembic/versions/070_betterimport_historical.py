"""BetterImport — overlap-safe historical CSV import (data layer).

A club can pull its Cricket Australia (Grassroots) data first, then upload its
own historical spreadsheet (career or season-by-season summaries). The danger is
double-counting: the same player has data in BOTH sources (e.g. Wayne Giles —
225 games across two GR participant profiles, but 473 in the club's own book).
Naively adding the club's 473 to GR's 225 gives 698.

The guarantee
-------------
The import never stores a club's raw total additively. It stores the club's
figures as *authoritative truth* (``imported_stats``), and a reconciler derives
only the **non-GR remainder** into ``import_effective_deltas``:

  * per (player, season): GR wins — if GR already has the season, the imported
    season is dropped; otherwise it's emitted as a season delta.
  * per player: one career residual = ``max(0, club_total − GR − emitted)``.

Because the only thing ever *added* to GR is ``max(0, club − GR)``, the career
sum is pinned to the club's stated total and cannot exceed it. The reconciler
re-runs as the final pass of every org sync, so the residual auto-shrinks as GR
coverage grows — no re-import needed.

This migration adds the data layer (Strategy "A2"):

  * ``import_batches``       — one upload (draft → committed → undone), audit +
    the saved column-mapping template.
  * ``imported_stats``       — immutable record of what the club uploaded, with
    provenance. The source of truth, re-import, and undo.
  * ``import_effective_deltas`` — *derived*, fully regenerable by the reconciler.
    Read by the effective view via one new additive ``UNION ALL`` branch.

Non-breaking: ``import_effective_deltas`` is empty for every club until they
import, so the new view branch contributes nothing and single-club orgs read
byte-for-byte unchanged (mirrors migration 060's read-time, non-destructive
philosophy). The existing precedence guard on the ``api`` base branch is left
exactly as migration 060 wrote it.

Revision ID: 070
Revises: 069
Create Date: 2026-06-05

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = '070'
down_revision = '069'
branch_labels = None
depends_on = None


# ── The 4-branch view, identical to migration 060 (the WITH-org-scope body).
#    Used as-is on downgrade, and as the base the import branch is appended to.
_VIEW_4_BRANCH = """
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
"""

# ── The new 5th branch: import-derived deltas. Additive and org-authored, so it
#    needs no cross-club guard. Derived stats (avg/SR/econ) are NULL — recomputed
#    on read by aggregations.py, exactly like the manual branches.
_IMPORT_BRANCH = """

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

_VIEW_5_BRANCH = _VIEW_4_BRANCH + _IMPORT_BRANCH


# Stat columns shared by imported_stats (named like manual_career_adjustments).
def _imported_truth_stat_columns():
    return [
        sa.Column('games_played', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_not_outs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_balls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_fours', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_sixes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_fifties', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_hundreds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_ducks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_high_score', sa.Integer(), nullable=True),
        sa.Column('batting_high_score_not_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('bowling_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_overs', sa.Numeric(8, 1), nullable=False, server_default='0'),
        sa.Column('bowling_balls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_maidens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_wickets', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_wides', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_no_balls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_five_wicket_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('bowling_best_wickets', sa.Integer(), nullable=True),
        sa.Column('bowling_best_figures', sa.Text(), nullable=True),
        sa.Column('fielding_catches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fielding_catches_wk', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fielding_run_outs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fielding_stumpings', sa.Integer(), nullable=False, server_default='0'),
    ]


# View-shaped count columns for import_effective_deltas (regenerable, derived).
def _delta_stat_columns():
    return [
        sa.Column('matches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('batting_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('runs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('not_outs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('balls_faced', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fifties', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('hundreds', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('ducks', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('fours', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sixes', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('high_score', sa.Integer(), nullable=True),
        sa.Column('is_hs_not_out', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('bowling_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('wickets', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('overs', sa.Numeric(8, 1), nullable=False, server_default='0'),
        sa.Column('bowling_balls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('runs_conceded', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('maidens', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('best_bowling_wickets', sa.Integer(), nullable=True),
        sa.Column('best_bowling_figures', sa.Text(), nullable=True),
        sa.Column('five_wicket_innings', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('wides', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('no_balls', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('catches', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('catches_wk', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('run_outs', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('stumpings', sa.Integer(), nullable=False, server_default='0'),
    ]


def upgrade() -> None:
    op.create_table(
        'import_batches',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('filename', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='draft'),
        sa.Column('granularity', sa.Text(), nullable=True),
        sa.Column('column_mapping', postgresql.JSONB(), nullable=False, server_default='{}'),
        sa.Column('row_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_by_user_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('committed_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('undone_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('ix_import_batches_org', 'import_batches', ['organisation_id'])

    op.create_table(
        'imported_stats',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('import_batch_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('import_batches.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        # 'career' = a whole-career total row; 'season' = one season's total.
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('seasons.id', ondelete='SET NULL'), nullable=True),
        sa.Column('season_label', sa.Text(), nullable=True),
        sa.Column('grade_label', sa.Text(), nullable=True),
        # The club's explicit "Prior Seasons & Adjustments" catch-all row, if any.
        sa.Column('is_prior_bucket', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        *_imported_truth_stat_columns(),
        # What the club literally provided (for verification + display). The raw
        # component columns above are reconstructed from these when absent.
        sa.Column('provided_batting_average', sa.Numeric(8, 2), nullable=True),
        sa.Column('provided_batting_strike_rate', sa.Numeric(8, 2), nullable=True),
        sa.Column('provided_bowling_average', sa.Numeric(8, 2), nullable=True),
        sa.Column('provided_bowling_economy', sa.Numeric(6, 2), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_imported_stats_org_player', 'imported_stats', ['organisation_id', 'player_id'])
    # One active truth row per (player, scope, season, grade). Re-import upserts;
    # this stops two live rows for the same cell from silently double-counting.
    op.execute(
        """
        CREATE UNIQUE INDEX uq_imported_stats_key ON imported_stats
        (organisation_id, player_id, scope,
         COALESCE(season_id, '00000000-0000-0000-0000-000000000000'::uuid),
         COALESCE(grade_label, ''))
        """
    )

    op.create_table(
        'import_effective_deltas',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('organisation_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scope', sa.Text(), nullable=False),
        sa.Column('season_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('seasons.id', ondelete='SET NULL'), nullable=True),
        sa.Column('grade_id', postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('grades.id', ondelete='SET NULL'), nullable=True),
        *_delta_stat_columns(),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
    )
    op.create_index('ix_import_deltas_org_player', 'import_effective_deltas', ['organisation_id', 'player_id'])

    # Re-create the effective view with the 5th (import) branch.
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute(_VIEW_5_BRANCH)


def downgrade() -> None:
    # Restore the 4-branch (migration 060) view before dropping the new tables.
    op.execute("DROP VIEW IF EXISTS v_effective_player_season_stats")
    op.execute(_VIEW_4_BRANCH)

    op.drop_index('ix_import_deltas_org_player', table_name='import_effective_deltas')
    op.drop_table('import_effective_deltas')
    op.execute("DROP INDEX IF EXISTS uq_imported_stats_key")
    op.drop_index('ix_imported_stats_org_player', table_name='imported_stats')
    op.drop_table('imported_stats')
    op.drop_index('ix_import_batches_org', table_name='import_batches')
    op.drop_table('import_batches')
