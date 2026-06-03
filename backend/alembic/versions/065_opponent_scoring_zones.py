"""add scoring_zones to opponent_player_tags (scout-entered wagon wheel)

BetterIQ's WagonWheel shows an opponent batter's scoring zones (% of runs by
area). CA community scoring has NO shot-direction data (verified against the
ball-by-ball feed — runs/wickets only), so zones are necessarily scout-entered.
Store them as an 8-number JSON array alongside the existing per-player tags.

Revision ID: 065
Revises: 064
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision = '065'
down_revision = '064'
branch_labels = None
depends_on = None


def upgrade():
    # 8 sectors, batter's view: Straight, Cover, Point, Third man, Fine leg,
    # Sq leg, Mid-wkt, Long-on — each a % of runs (scout-entered).
    op.add_column('opponent_player_tags', sa.Column('scoring_zones', JSONB(), nullable=True))


def downgrade():
    op.drop_column('opponent_player_tags', 'scoring_zones')
