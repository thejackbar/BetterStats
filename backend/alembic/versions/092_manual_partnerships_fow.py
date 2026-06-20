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
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '092'
down_revision = '091'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'manual_fall_of_wickets',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('manual_game_id', UUID(as_uuid=True), nullable=False),
        sa.Column('innings_number', sa.Integer(), nullable=False),
        sa.Column('wicket_number', sa.Integer(), nullable=False),
        sa.Column('score_at_fall', sa.Integer(), nullable=True),
        sa.Column('overs_at_fall', sa.Numeric(5, 1), nullable=True),
        sa.Column('player_id', UUID(as_uuid=True), nullable=True),
        sa.Column('batter_name', sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(['manual_game_id'], ['manual_games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_manual_fow_game', 'manual_fall_of_wickets', ['manual_game_id'])

    op.create_table(
        'manual_partnerships',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('manual_game_id', UUID(as_uuid=True), nullable=False),
        sa.Column('innings_number', sa.Integer(), nullable=False),
        sa.Column('wicket_number', sa.Integer(), nullable=False),
        sa.Column('batter1_id', UUID(as_uuid=True), nullable=True),
        sa.Column('batter2_id', UUID(as_uuid=True), nullable=True),
        sa.Column('runs', sa.Integer(), server_default='0', nullable=True),
        sa.Column('balls', sa.Integer(), nullable=True),
        sa.Column('batter1_runs', sa.Integer(), nullable=True),
        sa.Column('batter2_runs', sa.Integer(), nullable=True),
        sa.Column('is_club_innings', sa.Boolean(), nullable=True),
        sa.ForeignKeyConstraint(['manual_game_id'], ['manual_games.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['batter1_id'], ['players.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['batter2_id'], ['players.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_manual_partnerships_game', 'manual_partnerships', ['manual_game_id'])

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
