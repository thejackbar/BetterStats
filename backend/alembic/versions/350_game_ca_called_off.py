"""A fixture CA called off but left COMPLETED stops counting as a match played

`games.ca_called_off` is TRUE when both teams on CA's scorecard carry a resultType of ABANDONED while
the fixture's status still reads COMPLETED (Leederville CC, 14 Nov 2020: six games, "Match drawn",
and about twenty players one match over PlayCricket). CA does not count a named-only player in those.
Nothing else on the row says so: `result` is NULL, `status` reads COMPLETED and the opposition scored
19 to 22 overs, so neither the status rule nor the empty-scorecard rule fires. A genuine draw carries
DREW and is unaffected.

NULL (every existing row) means "not read" and counts as it always did, so nothing changes until the
sync or `app.scripts.backfill_ca_called_off` has read a game. The matches-played rules then treat TRUE
like an ABANDONED status for the games we hold: only a player with no batting, bowling or fielding row
of their own loses the match. CA's own total is reduced only as far as it runs past those games, since
CA leaves a named-only player out of these games and the total is usually already right.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290, 292, 293, 303, 309 and 349 also run: the new
column comes first in that list and the views that read it are re-issued after. Every statement is
idempotent.

Revision ID: 350
Revises: 349
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "350"
down_revision = "349"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # The views read ca_called_off, so they go back to the earlier definitions only by re-running the
    # previous statement list; the column is left in place, harmless and NULL.
    pass
