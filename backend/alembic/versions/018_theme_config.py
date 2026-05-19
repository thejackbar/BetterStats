"""Add per-club theme_config for expanded white-labelling

Revision ID: 018
Revises: 017
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '018'
down_revision = '017'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('organisations', sa.Column('theme_config', postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column('organisations', 'theme_config')
