"""Captain and wicket keeper on a hand-entered or imported game.

`manual_game_roles`: one row per player flagged captain and/or wicket keeper in a manual game.

Runs services/manual_game_roles_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 377
Revises: 376
"""
from alembic import op

from app.services.manual_game_roles_ddl import STATEMENTS, DOWNGRADE

revision = "377"
down_revision = "376"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
