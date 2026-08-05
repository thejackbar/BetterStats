"""Confirming a roster: the hours actually worked, checked and approved.

A rostered shift is what the club INTENDED. What a volunteer actually did is a
separate number, and until now nothing recorded it: the hours ledger could only
be filled in by hand, from a screen that had no idea the roster existed.

``roster_shifts.worked_hours`` is the roster's own record of what was worked,
adjustable while the week is being checked and surviving navigation away
mid-check. Confirming the roster posts those hours into ``volunteer_hours``,
which stays the club's ledger. The two are linked by
``volunteer_hours.roster_shift_id`` (migration 221), so confirming a corrected
week updates the posted rows in place instead of stacking a second copy on top.
The flow is deliberately one-way: the roster posts to the ledger, never the
reverse.

Revision ID: 222
Revises: 221
"""
from alembic import op

revision = "222"
down_revision = "221"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # NULL means "not checked yet", which is different from a checked zero
    # (someone was rostered and did not turn up). Both have to be expressible.
    op.execute("ALTER TABLE roster_shifts ADD COLUMN IF NOT EXISTS worked_hours NUMERIC(5,2)")

    # Who confirmed the roster, and when.
    op.execute("ALTER TABLE roster_weeks ADD COLUMN IF NOT EXISTS confirmed_at TIMESTAMPTZ")
    op.execute("ALTER TABLE roster_weeks ADD COLUMN IF NOT EXISTS confirmed_by_user_id UUID")

    # One posted ledger row per shift, so confirming twice corrects rather than
    # duplicates. Partial, because hours logged by hand carry no shift at all.
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_volunteer_hours_shift
        ON volunteer_hours(roster_shift_id) WHERE roster_shift_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_volunteer_hours_shift")
    op.execute("ALTER TABLE roster_weeks DROP COLUMN IF EXISTS confirmed_by_user_id")
    op.execute("ALTER TABLE roster_weeks DROP COLUMN IF EXISTS confirmed_at")
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS worked_hours")
