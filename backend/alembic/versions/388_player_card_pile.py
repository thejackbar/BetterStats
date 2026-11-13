"""Player Cards: the pile, spares a player has flagged for swapping

Defined once in services/player_card_pile_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 388
Revises: 387
"""
from alembic import op

from app.services.player_card_pile_ddl import STATEMENTS, DOWNGRADE

revision = "388"
down_revision = "387"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
