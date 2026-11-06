"""Player Cards: Winner Winner packs, the club's switch and the day they start

Defined once in services/player_card_winner_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 383
Revises: 382
"""
from alembic import op

from app.services.player_card_winner_ddl import STATEMENTS, DOWNGRADE

revision = "383"
down_revision = "382"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
