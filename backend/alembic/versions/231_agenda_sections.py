"""An agenda item belongs to a section.

A club's order of business is grouped, not flat: opening formalities, then the
reports, then elections, then general business, then closing. The agenda was a
single ordered list with no way to say which part of the meeting an item
belonged to, so a 20-item AGM read as one undifferentiated column.

`section` is a label on the item rather than a table of its own. The agenda
stays ONE ordered sequence (`position`), which is what keeps drag-to-reorder
working exactly as it did; the screen draws a heading wherever the section
changes. A section table would buy draggable and empty sections at the cost of
a join and a second thing to maintain, and a section with no items in it is not
a state a meeting needs to be able to hold.

Revision ID: 231
Revises: 230
"""
from alembic import op

revision = "231"
down_revision = "230"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE meeting_agenda_items ADD COLUMN IF NOT EXISTS section TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE meeting_agenda_items DROP COLUMN IF EXISTS section")
