"""Honour boards: an optional "only awards named" filter on an auto board.

`club_honour_boards.source_achievement` (NULL = every award in the category).
Nothing existing is changed.

Runs services/honour_board_achievement_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 343
Revises: 342
"""
from alembic import op

from app.services.honour_board_achievement_ddl import STATEMENTS, DOWNGRADE

revision = "343"
down_revision = "342"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
