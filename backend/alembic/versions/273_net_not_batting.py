"""Turning up and batting are two different facts.

``net_attendance.bats``
    The queue used to hold only one of them. A player who arrives carrying an
    injury — or to bowl, or to keep — is PRESENT: their attendance counts, and
    the club's report should say they were there. Putting them in the batting
    rotation means a net stands empty when their turn comes up. ``bats = false``
    keeps the row and takes it out of the queue.

``net_attendance.note``
    What they said on the way in ("sore shoulder", "bowling only"). Free text,
    capped in the router. Never required.

``source`` and the club's check-in link arrived a migration earlier (272), which
is why they aren't here.

Revision ID: 273
Revises: 272
"""
from alembic import op

revision = "273"
down_revision = "272"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS bats BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS note TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS bats")
