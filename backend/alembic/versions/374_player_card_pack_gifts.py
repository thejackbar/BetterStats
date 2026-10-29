"""Player Cards: packs a club creates by hand, and a quality for any pack

Defined once in services/player_card_gifts_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 374
Revises: 373
"""
from alembic import op

from app.services.player_card_gifts_ddl import STATEMENTS, DOWNGRADE

revision = "374"
down_revision = "373"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
