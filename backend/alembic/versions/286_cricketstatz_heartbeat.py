"""A heartbeat on a CricketStatz import

A full history is thousands of matches and takes the best part of an hour, so
the same figures sitting on screen for a minute is the ordinary case. Without a
record of when the row last moved there is nothing to tell that apart from a
run that has died, which is how a working import reads as a hung one.

Its own migration rather than an edit to 285, which is already applied.

Revision ID: 286
Revises: 285
Create Date: 2026-09-06
"""
from alembic import op

from app.services.cricketstatz_ddl import STATEMENTS  # noqa: E402

revision = "286"
down_revision = "285"
branch_labels = None
depends_on = None

_HEARTBEAT = [s for s in STATEMENTS if "updated_at" in s]


def upgrade() -> None:
    for statement in _HEARTBEAT:
        op.execute(statement)


def downgrade() -> None:
    op.execute("ALTER TABLE cricketstatz_imports DROP COLUMN IF EXISTS updated_at")
