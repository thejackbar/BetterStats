"""BetterClubManager Facilities — booking-requests approval queue.

A request to use a facility, checked against every confirmed booking on that
space before approval (conflict detection). Approving a clean request creates a
real facility_booking; declining just closes it.

Mirrored idempotently in app/main.py lifespan (migration 209 block).
"""
from alembic import op

revision = "209"
down_revision = "208"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS facility_booking_requests (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        facility_id UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        starts_at TIMESTAMPTZ NOT NULL,
        ends_at TIMESTAMPTZ NOT NULL,
        requester_name TEXT,
        requester_email TEXT,
        note TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        decided_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_facility_booking_requests_org ON facility_booking_requests(organisation_id, status)",
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    op.execute("DROP TABLE IF EXISTS facility_booking_requests CASCADE")
