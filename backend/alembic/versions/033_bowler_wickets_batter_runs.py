"""Add batter_runs / batter_balls to bowler_wickets so we can derive 'ducks
inflicted' style reports without needing opposition batting tables.

Revision ID: 033
Revises: 032
Create Date: 2026-05-26

batting_innings only stores OUR club's batters, so the old ducks_inflicted
query (which joined bowler_wickets → batting_innings on innings+position)
silently returned 0 rows — opposition batters never appear in
batting_innings, but they're the only ones our bowlers dismiss.

Denormalising the dismissed batter's runs + balls onto bowler_wickets
itself lets us answer 'ducks inflicted' / 'golden ducks inflicted' from
the one table. Sync is updated to populate these. Existing rows stay NULL
until the next Full Rebuild repopulates them.
"""
from alembic import op
import sqlalchemy as sa


revision = '033'
down_revision = '032'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('bowler_wickets', sa.Column('batter_runs', sa.Integer(), nullable=True))
    op.add_column('bowler_wickets', sa.Column('batter_balls', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('bowler_wickets', 'batter_balls')
    op.drop_column('bowler_wickets', 'batter_runs')
