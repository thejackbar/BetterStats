"""Player Cards: swap requests between two players

Defined once in services/player_card_swaps_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 364
Revises: 363
"""
from alembic import op

from app.services.player_card_swaps_ddl import STATEMENTS, DOWNGRADE

revision = "364"
down_revision = "363"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
