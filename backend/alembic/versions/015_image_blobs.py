"""Store club logo and player photo images in the database

Revision ID: 015
Revises: 014
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa

revision = '015'
down_revision = '014'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('organisations', sa.Column('logo_data', sa.LargeBinary(), nullable=True))
    op.add_column('organisations', sa.Column('logo_mime', sa.Text(), nullable=True))
    op.add_column('players', sa.Column('photo_data', sa.LargeBinary(), nullable=True))
    op.add_column('players', sa.Column('photo_mime', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('players', 'photo_mime')
    op.drop_column('players', 'photo_data')
    op.drop_column('organisations', 'logo_mime')
    op.drop_column('organisations', 'logo_data')
