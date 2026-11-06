"""BetterSelect votes: a team can be voted by a chosen group of people

The first release (347) let a captain-only team name ONE person to submit its
votes. A club may want a few people who make the decision together, so a team
can now be on a 'chosen' voter mode with a list of people, each submitting their
own ballot. This turns the stored single ids into lists of one and moves their
teams onto 'chosen'. Only entries still holding a bare id are touched, so it is
safe to run again.

Defined once in services/vote_medal_ddl.py, which main.py's lifespan mirror also
runs. Idempotent.

Revision ID: 362
Revises: 361
"""
from alembic import op

from app.services.vote_medal_ddl import VOTE_CHOSEN_VOTER_STATEMENTS

revision = "362"
down_revision = "361"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in VOTE_CHOSEN_VOTER_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Nothing to undo: see VOTE_CHOSEN_VOTER_DOWNGRADE.
    pass
