"""Add display_order column to seasons for admin reordering

Revision ID: 010
Revises: 009
Create Date: 2026-05-14
"""
from alembic import op
import sqlalchemy as sa

revision = '010'
down_revision = '009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('seasons', sa.Column('display_order', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('seasons', 'display_order')
