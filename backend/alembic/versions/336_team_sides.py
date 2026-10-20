"""A squad can cover several teams.

`team_sides` links a squad to the grades (teams) it covers, in order. A squad with
no rows is the old single-grade squad, so every existing club reads as before.

Runs services/team_sides_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 336
Revises: 335
"""
from alembic import op

from app.services.team_sides_ddl import STATEMENTS, DOWNGRADE

revision = "336"
down_revision = "335"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
