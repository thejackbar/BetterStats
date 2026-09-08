"""A suggested grade pair a club has said is not a duplicate

Manage Grades now proposes grade names that look like one grade under two
spellings. A club that has looked at a pair and decided the two really are
different grades must be able to say so once and never be asked again — the
same escape hatch `merge_pair_ignores` gives the player suggestions.

Keyed on the NAMES, not on grade ids, because a grade name spans one row per
season and every merge on this screen is name-to-name. Names are stored in
sorted order and written that way by the endpoint, so one pair is one row
whichever way round it was dismissed.

Revision ID: 291
Revises: 290
"""
from alembic import op

from app.services.grade_ignore_ddl import STATEMENTS

revision = "291"
down_revision = "290"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS grade_merge_pair_ignores")
