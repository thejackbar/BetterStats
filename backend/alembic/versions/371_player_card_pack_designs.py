"""Player Cards: a club's own designs for its packs

Defined once in services/player_card_designs_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 371
Revises: 370
"""
from alembic import op

from app.services.player_card_designs_ddl import STATEMENTS, DOWNGRADE

revision = "371"
down_revision = "370"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
