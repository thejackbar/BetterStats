"""Club history on the club, and a club-chosen reading order for grades.

Three columns, all nullable, all "unset means behave exactly as before":

``organisations.established_year``
    The year a club was founded, shown under its name on the public dashboard.
    A plain integer rather than a date: a club writes "Est. 1889", and almost
    none of them hold the founding day. An integer also sorts and subtracts,
    which a free-text "c.1890" never could.

``organisations.previous_names``
    A JSONB list of ``{"name": ..., "from_year": ..., "to_year": ...}``, oldest
    first. Both years are optional, because a club that knows it used to be
    Hampton Football Club often does not know when the name changed - and a
    shape that demands the years would leave that club unable to record the
    name at all.

``grades.display_order``
    The order a club reads its own teams in - Seniors 1, Reserves 2, Under 19s
    3. Every grade surface until now sorted alphabetically or by category,
    neither of which is the order a club would choose. NULL sorts last, so a
    grade nobody has ordered yet falls to the bottom of the ordered ones and
    keeps its existing alphabetical position among its unordered peers.
    Attaches per grade ROW (one per season), and the admin sets it across a
    whole grade name at once, the same way display_name_override and category
    already attach club-wide.

Revision ID: 226
Revises: 225
"""
from alembic import op

revision = "226"
down_revision = "225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS established_year INTEGER")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS previous_names JSONB")
    op.execute("ALTER TABLE grades ADD COLUMN IF NOT EXISTS display_order INTEGER")


def downgrade() -> None:
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS display_order")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS previous_names")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS established_year")
