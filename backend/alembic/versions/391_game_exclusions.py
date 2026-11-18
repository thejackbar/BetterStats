"""A club can mark a player as not having played a synced game (12th man, 13th man, late withdrawal).

`game_exclusions` (the club's mark, no foreign key to `games` so a Full Rebuild keeps it) and
`game_check_dismissals` (a "Games to check" suggestion the club kept as played).

Runs services/game_exclusion_ddl.STATEMENTS, the same list main.py's lifespan runs. Every
statement is idempotent.

Revision ID: 391
Revises: 390
"""
from alembic import op

from app.services.game_exclusion_ddl import STATEMENTS, DOWNGRADE

revision = "391"
down_revision = "390"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
