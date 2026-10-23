"""Fantasy rounds remember the kick-off of their first match: fantasy_rounds.first_start

The default lock time is one hour before the first match of the round, in the club's own
timezone. Defined once in services/fantasy_first_start_ddl.py, which main.py's lifespan
mirror also runs.

Revision ID: 360
Revises: 359
"""
from alembic import op

from app.services.fantasy_first_start_ddl import STATEMENTS, DOWNGRADE

revision = "360"
down_revision = "359"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
