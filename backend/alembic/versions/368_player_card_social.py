"""Player Cards: wish list, open to offers, alert settings and log, counter offers and a note on a swap

Defined once in services/player_card_social_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 368
Revises: 367
"""
from alembic import op

from app.services.player_card_social_ddl import STATEMENTS, DOWNGRADE

revision = "368"
down_revision = "367"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
