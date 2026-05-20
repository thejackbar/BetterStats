"""add game_appearances table

Revision ID: 022
Revises: 021
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '022'
down_revision = '021'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'game_appearances',
        sa.Column('game_id', UUID(as_uuid=True), sa.ForeignKey('games.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_name', sa.Text(), nullable=True),
        sa.Column('is_captain', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_wicket_keeper', sa.Boolean(), nullable=False, server_default='false'),
        sa.PrimaryKeyConstraint('game_id', 'player_id', name='pk_game_appearances'),
    )
    op.create_index('ix_game_appearances_player', 'game_appearances', ['player_id'])


def downgrade():
    op.drop_index('ix_game_appearances_player', table_name='game_appearances')
    op.drop_table('game_appearances')
