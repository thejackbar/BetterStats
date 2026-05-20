"""Add gender, is_player, player_role to players

Revision ID: 023
Revises: 022
Create Date: 2026-05-20
"""
from alembic import op
import sqlalchemy as sa

revision = '023'
down_revision = '022'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('players', sa.Column('gender', sa.Text(), nullable=True))
    op.add_column('players', sa.Column('is_player', sa.Boolean(), nullable=True, server_default='true'))
    op.add_column('players', sa.Column('player_role', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('players', 'player_role')
    op.drop_column('players', 'is_player')
    op.drop_column('players', 'gender')
