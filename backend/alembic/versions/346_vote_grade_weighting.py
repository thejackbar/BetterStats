"""BetterSelect votes: weight grades by season length

A grade that plays 12 games and one that plays 18 hand out the same points per
vote, so a player in the longer season has more chances to collect them.
``vote_medals.grade_weighting`` holds how a medal corrects for that: off, auto
(from fixture counts against the top grade) or manual per grade NAME. Empty
means no weighting.

Defined once in services/vote_medal_ddl.py, which main.py's lifespan mirror also
runs. Idempotent.

Revision ID: 346
Revises: 345
"""
from alembic import op

from app.services.vote_medal_ddl import VOTE_GRADE_WEIGHT_STATEMENTS, VOTE_GRADE_WEIGHT_DOWNGRADE

revision = "346"
down_revision = "345"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in VOTE_GRADE_WEIGHT_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in VOTE_GRADE_WEIGHT_DOWNGRADE:
        op.execute(statement)
