"""BetterMerch — per-product tracking mode (for_resale)

Splits stock into bought-to-sell (cost + sell price, margin, member owing — e.g.
apparel and canteen) vs club-use consumable (a straight cost, no sell price — e.g.
match/training balls). Defaults true so existing rows keep their cost+price model;
the New Product form defaults equipment to club-use.

Mirrored idempotently in main.py's lifespan.

Revision ID: 085
Revises: 084
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa


revision = '085'
down_revision = '084'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('merch_products', sa.Column('for_resale', sa.Boolean(), nullable=False, server_default='true'))


def downgrade() -> None:
    op.drop_column('merch_products', 'for_resale')
