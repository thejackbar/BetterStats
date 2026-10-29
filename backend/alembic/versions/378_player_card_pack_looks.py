"""Player Cards: a pack made by hand can be designed and sized as it is made

Defined once in services/player_card_looks_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 378
Revises: 377
"""
from alembic import op

from app.services.player_card_looks_ddl import STATEMENTS, DOWNGRADE

revision = "378"
down_revision = "377"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
