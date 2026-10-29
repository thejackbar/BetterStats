"""Player Cards: the club's setting for which cards get the big photo

Defined once in services/player_card_photos_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 376
Revises: 375
"""
from alembic import op

from app.services.player_card_photos_ddl import STATEMENTS, DOWNGRADE

revision = "376"
down_revision = "375"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
