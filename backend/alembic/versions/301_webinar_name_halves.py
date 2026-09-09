"""A registrant's first and last name, kept rather than guessed

Reported after the StreamYard push started skipping people: "Can you double
check the form then because it does say first and last name so it should be
pulling across."

It was right to expect that and the form was the mismatch. StreamYard's own
registration form has First name and Last name as separate REQUIRED fields —
verified against the live endpoint, a blank surname is a 400 — while ours asked
for one field labelled YOUR NAME. So a registrant who typed a single word left
nothing to send, and the push skipped them.

SPLITTING ONE STRING IS NOT A FIX, IT IS A GUESS. At a space it gets "Mary Jane
Smith" wrong (first name "Mary", surname "Jane Smith") and has no answer at all
for a mononym. The form asks for the two halves now and this keeps them, so
what goes to StreamYard is what the person actually typed.

`name` STAYS AND STAYS AUTHORITATIVE for everything that reads a name — the
confirmation email's greeting, the reminder, the staff list, the CSV export.
The halves sit alongside it, so nothing downstream changed and no backfill is
needed. Both nullable on purpose: a row written before this genuinely only ever
had one string, and NULL is the honest record of that. `push_to_streamyard`
prefers the halves when they are there and falls back to splitting `name` when
they are not, so an older registration still pushes exactly as it did.

Re-runs the whole shared `webinar_ddl.STATEMENTS` list rather than issuing two
lone ALTERs — every statement is idempotent, so a database at any of 296, 297,
299, 300 or 301 lands on the same schema. One list, no second copy to drift.

Revision ID: 301
Revises: 300
"""
from alembic import op

from app.services.webinar_ddl import STATEMENTS

revision = "301"
down_revision = "300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Narrow, the same call 297, 299 and 300 made: 296 owns the table, so
    # undoing THIS migration drops only what it added. Dropping the table would
    # destroy every registration over two columns.
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS first_name")
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS last_name")
