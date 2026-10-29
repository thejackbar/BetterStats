"""Player Cards: showcase, collectors board and feed opt-ins, and the club's switches for sets, showcase, board and feed

Defined once in services/player_card_community_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 369
Revises: 368
"""
from alembic import op

from app.services.player_card_community_ddl import STATEMENTS, DOWNGRADE

revision = "369"
down_revision = "368"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
