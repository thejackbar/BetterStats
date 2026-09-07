"""Configurable club notifications

A club could not choose what it was told about. The notification bell computed
a fixed set of sections live from source data, and the only outbound email a
club admin ever received was a trial nudge from BetterCricket's own sales
automation — so a milestone passed unremarked unless somebody happened to open
the bell, and a volunteer's Working With Children check could lapse with nobody
warned at all.

This adds the record and the switches: what happened, who was told, which
events a club wants, on which channels, and each admin's own opt-out. The
catalogue of events itself stays in code (services/notification_events.py) —
every event needs a source that can find it, so a row describing one nothing
can produce would be a promise the platform cannot keep.

Revision ID: 287
Revises: 286
Create Date: 2026-09-07
"""
from alembic import op

from app.services.notification_ddl import DOWNGRADE, STATEMENTS  # noqa: E402

revision = "287"
down_revision = "286"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
