"""The crawl re-reads an existing club's associations

Reported as a gap in what "start crawling" does: the crawl was expected to
re-discover existing clubs and pick up changes in address, associations and
officers. It already refreshes the address (``_upsert_club`` rewrites name,
website, suburb, state, postcode and coordinates on every pass) and already
adds newly listed officers — but the association enrichment frontier is
``associations IS NULL``, so a club's associations were fetched once and then
never looked at again. A club that moved association kept the old one for
ever.

``associations_fetched_at`` is what makes a refresh expressible.
``last_crawled_at`` cannot do it: the discovery pass bumps that for every club
it sees, so it records when the club was last SEEN rather than when its
associations were last READ.

Revision ID: 298
Revises: 297
"""
from alembic import op

from app.services.assoc_refresh_ddl import STATEMENTS

revision = "298"
down_revision = "297"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Dropping the column puts the frontier back to "associations IS NULL", which
    # is exactly the pre-298 behaviour — no data other than the timestamps is
    # lost, since the associations themselves live in their own column.
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS associations_fetched_at")
