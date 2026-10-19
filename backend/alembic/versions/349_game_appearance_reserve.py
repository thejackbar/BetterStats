"""A 12th man who did not play stops counting as a match played

`game_appearances.is_reserve` marks a player who was named on the team sheet and nothing
else: their side batted, they are not on its batting card (not even as Did Not Bat), they have
no bowling or fielding row, and they sit beyond slot 11. CA's scorecard has no substitute
marker, so the call is made from the shape of the card (services/reserve_players.py), by the
sync for new games and by scripts/backfill_reserve_flags.py for games already stored.

NULL (every existing row) means "not judged" and is read as a player who played, so nothing
changes until a club's games have been read.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290, 292, 293, 303 and 309 also run:
the new columns come first in that list and the views that read them are re-issued after.
Every statement is idempotent.

Revision ID: 349
Revises: 348
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "349"
down_revision = "348"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # The views read is_reserve, so they go back to the pre-reserve definitions only by
    # re-running the previous statement list; the columns are left in place, harmless and NULL.
    pass
