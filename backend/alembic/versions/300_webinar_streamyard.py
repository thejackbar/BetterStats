"""Whether a registrant was pushed into StreamYard's own list

Asked for directly: "I want just one single form and the registrants to be put
into StreamYard as well as in BetterCricket rather than making someone register
twice."

The second form was StreamYard's own registration gate, which asks for email,
first name, last name and phone — every one of which our form already collects.
Removing it is a setting in StreamYard and nothing this code can reach; what
this code can do is push each registrant into their list anyway, so switching
the gate off costs them nothing.

Two columns rather than one boolean: the id when it worked (so a row can be
found at their end) and the reason when it did not. Both NULL means nothing has
tried yet. The push runs against an UNDOCUMENTED API and must never fail a
registration, so its failures have to be visible on the row instead of only in
a log.

Re-runs the whole shared `webinar_ddl.STATEMENTS` list rather than issuing two
lone ALTERs — every statement is idempotent, so a database at any of 296, 297,
299 or 300 lands on the same schema. One list, no second copy to drift.

Revision ID: 300
Revises: 299
"""
from alembic import op

from app.services.webinar_ddl import STATEMENTS

revision = "300"
down_revision = "299"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Narrow, the same call 297 and 299 made: 296 owns the table, so undoing
    # THIS migration drops only what it added. Dropping the table would destroy
    # every registration over two columns.
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS streamyard_id")
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS streamyard_error")
