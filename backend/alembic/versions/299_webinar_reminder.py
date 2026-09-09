"""A reminder on the day, and its outcome, on the registration

Asked for as the thing that makes turning StreamYard's own registration gate
off cost nothing. That gate is why a registrant fills a form twice — ours, then
StreamYard's — and switching it off is a setting in StreamYard rather than
anything this code can reach. The one thing it takes away is StreamYard's own
reminder email, so this is our replacement for it.

`reminder_sent_at` doubles as the CLAIM, not just the record: the sweep stamps
it before it sends, so two runs overlapping cannot both email the same person,
and a refusal clears it back to NULL so the next hour retries. A hard crash
between the stamp and the send leaves it claimed and the reminder is missed —
the conservative direction for the rarer case, since a duplicate reminder is
the one a registrant would notice.

Re-runs the whole of `webinar_ddl.STATEMENTS` rather than issuing two lone
ALTERs: every statement in that list is idempotent, so a database already at
297 picks up the added columns and one that has never had the table gets it
created with them already on it. One list, no second copy of a column
definition to drift.

NUMBERED 299, NOT 298 — `origin/main` reached 298 (`assoc_refresh`) while this
was in flight, and two migrations sharing a revision id break Alembic outright.
Check `origin/main` at the moment you merge, not only when you first number one.

Revision ID: 299
Revises: 298
"""
from alembic import op

from app.services.webinar_ddl import STATEMENTS

revision = "299"
down_revision = "298"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Deliberately narrow, the same call 297 made: 296 owns the table, so
    # undoing THIS migration drops only what it added. Dropping the table here
    # would destroy every registration over two columns.
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS reminder_sent_at")
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS reminder_error")
