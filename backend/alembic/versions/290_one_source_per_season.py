"""One source per season, decided by the data rather than by a step

287 let a club say CricketStatz was the record for a season it also syncs, and
worked the overlap out ONCE at the start of an import, marking the seasons as
it walked them. Anything that changed `games` in between — a Full Rebuild
finishing, a sync landing — left that snapshot wrong, and the club counted both
sources with nothing on screen to say so. Reported live: a career reading
14,966 runs against CricketStatz's 10,444, with every shared season holding
exactly synced + imported.

The rule is now an invariant rather than a procedure. A season that receives a
CricketStatz match is marked in the SAME transaction as the match, so a season
holding imported matches and no recorded source cannot exist; `'playhq'` steps
the imported side aside so handing a season back also counts one source rather
than both; and the backfill repairs any club already in that state, with no
re-import.

Re-runs services/superseded_ddl.STATEMENTS, which 287 also runs — every
statement is idempotent, so a database already at 287 simply picks up the added
clauses and the backfill.

Revision ID: 290
Revises: 289
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "290"
down_revision = "289"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # 287 owns the column and the views; there is nothing here to take back
    # that undoing 287 would not already remove.
    pass
