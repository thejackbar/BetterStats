"""BetterSelect votes: a nominated person counts a captain-only team's votes

A captain sometimes hands vote counting to someone else, who may not be in the
side. ``vote_medals.grade_vote_counters`` holds that person per team (grade
NAME to player id). Empty means the captain votes, as before.

Defined once in services/vote_medal_ddl.py, which main.py's lifespan mirror also
runs. Idempotent.

Revision ID: 347
Revises: 346
"""
from alembic import op

from app.services.vote_medal_ddl import VOTE_GRADE_COUNTER_STATEMENTS, VOTE_GRADE_COUNTER_DOWNGRADE

revision = "347"
down_revision = "346"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in VOTE_GRADE_COUNTER_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in VOTE_GRADE_COUNTER_DOWNGRADE:
        op.execute(statement)
