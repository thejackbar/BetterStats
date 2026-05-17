"""Add photo_url to players

Revision ID: 012
Revises: 011
Create Date: 2026-05-17
"""
from alembic import op
import sqlalchemy as sa

revision = '012'
down_revision = '011'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('players', sa.Column('photo_url', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('players', 'photo_url')
