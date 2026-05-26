"""add match_format to games

Revision ID: 033
Revises: 032
Create Date: 2026-05-26

Captures the cricket match format (T20 / One Day / Two Day+) from the
Grassroots scorecard so we can filter stats by format across StatLab,
Leaderboards, Records, Yearbook, etc. Backfilled on the next hard refresh
(also opportunistically backfilled during incremental syncs when a game
row exists with match_format IS NULL).
"""
from alembic import op
import sqlalchemy as sa


revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('games', sa.Column('match_format', sa.Text(), nullable=True))
    op.create_index('ix_games_match_format', 'games', ['match_format'])


def downgrade() -> None:
    op.drop_index('ix_games_match_format', 'games')
    op.drop_column('games', 'match_format')
