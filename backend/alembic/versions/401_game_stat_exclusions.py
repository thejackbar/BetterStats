"""A club can leave a whole match out of its players' stats (a friendly, a pre-season cup)

`game_stat_exclusions` holds the club's choice, one row per (club, match), with no foreign key to
`games` so a Full Rebuild keeps it, and `restored_at` set (never a delete) when the club counts the
match again. Only the club that made the choice loses the match: the other club on a shared fixture
keeps it. See services/stat_exclusions.py for how every figure follows.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290, 292, 293, 303, 309, 349 and 350 also run:
the table comes first in that list (services/stat_exclusion_ddl), then the views that read it, then
the two `v_card_*` copies the scorecard reads so an excluded match still shows whole. Every statement
is idempotent.

Revision ID: 401
Revises: 400
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "401"
down_revision = "400"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # As 350: the views go back to the earlier definitions only by re-running the previous statement
    # list. The table is left in place and the club's choices with it; with no code reading it, an
    # exclusion changes nothing.
    pass
