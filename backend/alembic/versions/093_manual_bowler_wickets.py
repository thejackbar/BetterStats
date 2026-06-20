"""manual bowler wickets, with an effective union view.

A manually-uploaded scorecard knows, for each opposition batter our side dismissed,
who bowled and who caught it. The synced per-wicket table `bowler_wickets` (FK'd to
`games`) powers BetterIQ's "how we take wickets", the bowler deep-dive, fielder→bowler
catching combos and opponent matchups. Give manual games the same per-wicket credit
with their own table (FK'd to `manual_games`) plus a v_effective union view, mirroring
migration 092. The bowling FIGURES already give wicket counts; this adds the
per-dismissal bowler/fielder/method detail.

Idempotent raw DDL so it coexists with the main.py lifespan mirror on this box's
layered schema (a plain CREATE TABLE that meets an existing object would abort the
whole upgrade and stop the backend booting).

Revision ID: 093
Revises: 092
Create Date: 2026-06-20
"""
from alembic import op


revision = '093'
down_revision = '092'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_bowler_wickets (
            id SERIAL PRIMARY KEY,
            manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
            innings_number INTEGER NOT NULL,
            bowler_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            fielder_id UUID REFERENCES players(id) ON DELETE SET NULL,
            batter_name TEXT,
            batter_position INTEGER,
            batter_runs INTEGER,
            batter_balls INTEGER,
            dismissal_type TEXT NOT NULL,
            caught_behind BOOLEAN
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_manual_bw_game ON manual_bowler_wickets(manual_game_id)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_manual_bw_bowler ON manual_bowler_wickets(bowler_id)")
    op.execute("""
        CREATE OR REPLACE VIEW v_effective_bowler_wickets AS
        SELECT id, game_id, innings_number, bowler_id, fielder_id, batter_name,
               batter_position, batter_runs, batter_balls, dismissal_type, caught_behind,
               'api'::text AS source
        FROM bowler_wickets
        UNION ALL
        SELECT id, manual_game_id AS game_id, innings_number, bowler_id, fielder_id, batter_name,
               batter_position, batter_runs, batter_balls, dismissal_type, caught_behind,
               'manual'::text AS source
        FROM manual_bowler_wickets
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_effective_bowler_wickets")
    op.execute("DROP INDEX IF EXISTS idx_manual_bw_bowler")
    op.execute("DROP INDEX IF EXISTS idx_manual_bw_game")
    op.drop_table('manual_bowler_wickets')
