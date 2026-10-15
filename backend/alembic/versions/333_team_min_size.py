"""A team's minimum side size.

`teams.min_team_size` is the fewest players a team may field (a women's or
junior side that needs 8 but may name 12). NULL is no minimum, so every
existing team behaves exactly as before: it is complete when it is full.

Runs services/team_min_size_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 333
Revises: 332
"""
from alembic import op

from app.services.team_min_size_ddl import STATEMENTS, DOWNGRADE

revision = "333"
down_revision = "332"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
