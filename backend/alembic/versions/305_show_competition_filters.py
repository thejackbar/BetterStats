"""Opt-in switch for the Competition filter row on public stats pages.

A club that has grouped its grades into competitions keeps the filter to itself
until it switches this on in its admin settings. Off by default, so no
established club's public pages change because of an upgrade. While it is on the
"All" pill means the sum of every competition the row lists rather than Cricket
Australia's own lifetime totals — see useGradeFilters on the frontend.

Revision ID: 305
Revises: 304
"""
from alembic import op

revision = "305"
down_revision = "304"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "show_competition_filters BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS show_competition_filters")
