"""Add overseas player fields to players table.

Revision ID: 036
Revises: 035
Create Date: 2026-05-26
"""
from alembic import op
import sqlalchemy as sa


revision = '036'
down_revision = '035'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('players', sa.Column('is_overseas', sa.Boolean(), nullable=True))
    op.add_column('players', sa.Column('overseas_country', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('players', 'overseas_country')
    op.drop_column('players', 'is_overseas')
