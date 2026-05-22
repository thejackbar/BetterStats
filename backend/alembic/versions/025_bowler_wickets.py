"""Add bowler_wickets table for bowler-perspective dismissal tracking

Revision ID: 025
Revises: 024
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'bowler_wickets',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('game_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('games.id', ondelete='CASCADE'), nullable=False),
        sa.Column('innings_number', sa.Integer(), nullable=False),
        sa.Column('bowler_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('fielder_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('batter_name', sa.Text(), nullable=True),
        sa.Column('batter_position', sa.Integer(), nullable=True),
        sa.Column('dismissal_type', sa.Text(), nullable=False),
    )
    op.create_index('ix_bowler_wickets_bowler_id', 'bowler_wickets', ['bowler_id'])
    op.create_index('ix_bowler_wickets_game_id', 'bowler_wickets', ['game_id'])


def downgrade():
    op.drop_index('ix_bowler_wickets_game_id', 'bowler_wickets')
    op.drop_index('ix_bowler_wickets_bowler_id', 'bowler_wickets')
    op.drop_table('bowler_wickets')
