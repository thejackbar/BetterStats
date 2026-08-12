"""fee_member_seasons — a PlayHQ registration checkbox

Playing this season requires the person to have registered with PlayHQ, and
nothing in this codebase can read that back from PlayHQ itself (no API for
it) — so it's a plain admin-ticked checkbox, per season, on the existing
fee_member_seasons row. ``playhq_registered_at`` records when it was ticked
(cleared if the box is unticked again), for "when did we last check".

Deliberately not carried forward by season rollover (services/fees.py
rollover_members never sets it) — registration is a per-season requirement,
so a rolled-over row always starts unticked and has to be reconfirmed.

Revision ID: 235
Revises: 234
"""
from alembic import op

revision = "235"
down_revision = "234"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS "
        "playhq_registered BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS "
        "playhq_registered_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE fee_member_seasons DROP COLUMN IF EXISTS playhq_registered_at")
    op.execute("ALTER TABLE fee_member_seasons DROP COLUMN IF EXISTS playhq_registered")
