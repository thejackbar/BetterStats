"""manual partnerships + fall of wickets, with effective union views.

The Upload Historical Scorecard tool reads the fall-of-wickets table (including the
STAND column = partnership runs) off the card, so a manually-uploaded game can carry
the same per-wicket partnership and fall data a synced game does. The synced
`partnerships` / `fall_of_wickets` tables are FK'd to `games`, so manual games need
their own tables (FK'd to `manual_games`), mirrored into `v_effective_*` union views
exactly like migration 038 did for batting / bowling / fielding.

Switching the per-game readers (the match scorecard) to the views lets an uploaded
card show its fall of wickets and partnerships. The analytics readers (BetterIQ
batting pairs / collapse / review) can move to the views the same way later.

Revision ID: 092
Revises: 091
Create Date: 2026-06-20
"""
from alembic import op


revision = '092'
down_revision = '091'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) so the migration
    # and the boot-time mirror can't collide. On this box the schema is layered (dump
    # + lifespan + alembic): a plain CREATE TABLE can hit an already-existing object
    # and abort `alembic upgrade head`, which then stops uvicorn from starting and
    # crash-loops the backend. IF NOT EXISTS makes re-runs and either ordering safe.
    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_fall_of_wickets (
            id SERIAL PRIMARY KEY,
            manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
            innings_number INTEGER NOT NULL,
            wicket_number INTEGER NOT NULL,
            score_at_fall INTEGER,
            overs_at_fall NUMERIC(5,1),
            player_id UUID REFERENCES players(id) ON DELETE SET NULL,
            batter_name TEXT
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_manual_fow_game ON manual_fall_of_wickets(manual_game_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS manual_partnerships (
            id SERIAL PRIMARY KEY,
            manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
            innings_number INTEGER NOT NULL,
            wicket_number INTEGER NOT NULL,
            batter1_id UUID REFERENCES players(id) ON DELETE SET NULL,
            batter2_id UUID REFERENCES players(id) ON DELETE SET NULL,
            runs INTEGER DEFAULT 0,
            balls INTEGER,
            batter1_runs INTEGER,
            batter2_runs INTEGER,
            is_club_innings BOOLEAN
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS idx_manual_partnerships_game ON manual_partnerships(manual_game_id)")

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_fall_of_wickets AS
        SELECT
            id, game_id, innings_number, wicket_number,
            score_at_fall, overs_at_fall, player_id, batter_name,
            'api'::text AS source
        FROM fall_of_wickets
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, innings_number, wicket_number,
            score_at_fall, overs_at_fall, player_id, batter_name,
            'manual'::text AS source
        FROM manual_fall_of_wickets
    """)

    op.execute("""
        CREATE OR REPLACE VIEW v_effective_partnerships AS
        SELECT
            id, game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'api'::text AS source
        FROM partnerships
        UNION ALL
        SELECT
            id, manual_game_id AS game_id, innings_number, wicket_number,
            batter1_id, batter2_id, runs, balls,
            batter1_runs, batter2_runs, is_club_innings,
            'manual'::text AS source
        FROM manual_partnerships
    """)


def downgrade() -> None:
    op.execute("DROP VIEW IF EXISTS v_effective_partnerships")
    op.execute("DROP VIEW IF EXISTS v_effective_fall_of_wickets")
    op.drop_index('idx_manual_partnerships_game', table_name='manual_partnerships')
    op.drop_table('manual_partnerships')
    op.drop_index('idx_manual_fow_game', table_name='manual_fall_of_wickets')
    op.drop_table('manual_fall_of_wickets')
