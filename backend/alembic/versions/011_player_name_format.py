"""Add player_name_format column to organisations

Revision ID: 011
Revises: 010
Create Date: 2026-05-15
"""
from alembic import op
import sqlalchemy as sa

revision = '011'
down_revision = '010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organisations', sa.Column('player_name_format', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('organisations', 'player_name_format')
