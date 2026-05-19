"""add is_final to games

Revision ID: 021
Revises: 020
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '021'
down_revision = '020'
branch_labels = None
depends_on = None

def upgrade():
    op.add_column('games', sa.Column('is_final', sa.Boolean(), nullable=False, server_default='false'))

def downgrade():
    op.drop_column('games', 'is_final')
