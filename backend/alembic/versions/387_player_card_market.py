"""Player Cards: the Market, and a setting to keep a wish list out of it

Defined once in services/player_card_market_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 387
Revises: 386
"""
from alembic import op

from app.services.player_card_market_ddl import STATEMENTS, DOWNGRADE

revision = "387"
down_revision = "386"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
