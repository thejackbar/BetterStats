"""Player Cards: challenges (exchange and collection), their completions, and players' own private sets

Defined once in services/player_card_challenges_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 380
Revises: 379
"""
from alembic import op

from app.services.player_card_challenges_ddl import STATEMENTS, DOWNGRADE

revision = "380"
down_revision = "379"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
