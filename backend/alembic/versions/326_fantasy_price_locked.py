"""Fantasy price movement: fantasy_pool_players.price_locked

A price an admin typed in by hand is left alone by the round-by-round price
movement. Defined once in services/fantasy_price_ddl.py, which main.py's
lifespan mirror also runs.

Revision ID: 326
Revises: 325
"""
from alembic import op

from app.services.fantasy_price_ddl import STATEMENTS, DOWNGRADE

revision = "326"
down_revision = "325"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
