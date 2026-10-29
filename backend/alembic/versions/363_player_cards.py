"""Player Cards: packs, owned cards, special cards, hidden players and a club's card settings

Defined once in services/player_cards_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 363
Revises: 362
"""
from alembic import op

from app.services.player_cards_ddl import STATEMENTS, DOWNGRADE

revision = "363"
down_revision = "362"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
