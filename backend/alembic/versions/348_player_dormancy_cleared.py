"""BetterSelect: a dormant player can be marked "no longer dormant"

``players.dormancy_cleared_on`` is the day a club said a long-absent player is
back, so they show in availability, the squads board and selection in the weeks
before their first game. Read through services/dormancy.py. Nothing changes for
a player it is NULL on, which is everyone until a club uses it.

Defined once in services/dormancy_ddl.py, which main.py's lifespan mirror also
runs. Idempotent.

Revision ID: 348
Revises: 347
"""
from alembic import op

from app.services.dormancy_ddl import STATEMENTS, DOWNGRADE

revision = "348"
down_revision = "347"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
