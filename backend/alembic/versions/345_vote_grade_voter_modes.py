"""BetterSelect votes: a voter mode per team

A medal had one ``voter_mode`` for the whole club, but clubs run it differently
by team: the firsts count only the captain's votes, the juniors let every
player vote. ``vote_medals.grade_voter_modes`` holds an override per grade NAME
(names, not ids, so it survives the new season's grade rows). Empty means every
team follows the medal's own ``voter_mode``.

Defined once in services/vote_medal_ddl.py, which main.py's lifespan mirror also
runs. Idempotent.

Revision ID: 345
Revises: 344
"""
from alembic import op

from app.services.vote_medal_ddl import VOTE_GRADE_MODE_STATEMENTS, VOTE_GRADE_MODE_DOWNGRADE

revision = "345"
down_revision = "344"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in VOTE_GRADE_MODE_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in VOTE_GRADE_MODE_DOWNGRADE:
        op.execute(statement)
