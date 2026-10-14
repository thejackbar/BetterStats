"""A team's own number of players.

`teams.team_size` (NULL = follow the club default, 0 = no limit), so a women's
grade can pick ten and an OD6s side twelve without moving every other team.

Runs services/team_size_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent. Downgrade drops only the column added here.

Revision ID: 330
Revises: 329
"""
from alembic import op

from app.services.team_size_ddl import STATEMENTS, DOWNGRADE

revision = "330"
down_revision = "329"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
