"""A club's own default for which grade categories count towards its stats.

``organisations.stats_grade_categories`` is a JSONB list of category keys drawn
from ``grade_labels.GRADE_CATEGORIES`` — senior / junior / womens / masters /
mixed. NULL means "no club preference", and every club has NULL until an admin
sets one, so nothing about where the default comes from changes on upgrade.

The platform default it falls back to (``grade_scope.DEFAULT_CATEGORIES``) is
everything except junior: an Under-14 season inside a senior career average is
the reported problem, and Women's/Masters/Mixed are senior cricket that a club
should not have to switch back on.

The column is deliberately a list rather than a pair of booleans. There are five
categories today and clubs keep asking for splits we have not thought of yet; a
list absorbs a sixth without a second migration, and it is the same shape the
API takes on the wire.

Revision ID: 228
Revises: 227
"""
from alembic import op

revision = "228"
down_revision = "227"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stats_grade_categories JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stats_grade_categories")
