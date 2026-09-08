"""The two sources complement each other: pair the matches, keep both sides

287, 290 and 292 removed the double count by choosing ONE source per season —
which also threw away every match the losing source alone held. Measured across
five of one club's seasons, Cricket Australia had 401 matches and CricketStatz
473, each with genuine gaps the other filled.

So the duplicate is removed per MATCH instead: `manual_games.superseded_by_game_id`
pairs an imported match to the synced game that is the same match, and
`pair_prefers_import` says which half of the pair counts. Everything unpaired
from both sides counts. `seasons.stats_source` is left in place and read by
nothing.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290 and 292 also run.
Every statement is idempotent.

Revision ID: 293
Revises: 292
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "293"
down_revision = "292"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # 287 owns the column and the views; undoing it removes these too.
    pass
