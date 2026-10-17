"""A team's own side size.

`teams.default_team_size` lets one club run 12-a-side seconds next to 11-a-side
firsts. NULL follows the club default (`organisations.default_team_size`), so
every existing club behaves exactly as before.

Runs services/team_size_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 332
Revises: 331
"""
from alembic import op

from app.services.team_size_ddl import STATEMENTS, DOWNGRADE

revision = "332"
down_revision = "331"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
