"""Add did_not_bat flag to batting_innings

Revision ID: 013
Revises: 012
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = '013'
down_revision = '012'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('batting_innings', sa.Column('did_not_bat', sa.Boolean(), nullable=True, server_default='false'))


def downgrade():
    op.drop_column('batting_innings', 'did_not_bat')
