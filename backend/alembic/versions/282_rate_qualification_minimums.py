"""A club's own minimum before a strike rate or economy is published

A strike rate worked out from three innings is a real figure and is not the
same kind of figure as one worked out from thirty. A leaderboard that ranks the
two against each other is what this qualification exists to stop.

Two nullable columns rather than one setting with a default: NULL means the
club has expressed no preference and the platform default applies, which is 0.
Nothing has ever qualified these boards, so switching a number on for every
club would drop players off their own leaderboard the day it deployed without
anybody choosing it. A club picks its own number in Club Settings, and a viewer
can raise it for one look with the pills above the board.

Read through services/stats_display.py, never directly.

Revision ID: 282
Revises: 281
Create Date: 2026-09-01
"""
from alembic import op

from app.services.rate_qualification_ddl import (  # noqa: E402
    RATE_MINIMUM_DOWNGRADE,
    RATE_MINIMUM_STATEMENTS,
)

revision = "282"
down_revision = "281"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in RATE_MINIMUM_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in RATE_MINIMUM_DOWNGRADE:
        op.execute(stmt)
