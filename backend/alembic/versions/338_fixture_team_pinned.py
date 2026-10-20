"""A synced fixture whose squad was picked by hand is pinned.

`fixtures.team_pinned` (default false). Sync corrects a wrong automatic squad on
a synced fixture and leaves a pinned one alone.

Runs services/fixture_pin_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 338
Revises: 337
"""
from alembic import op

from app.services.fixture_pin_ddl import STATEMENTS, DOWNGRADE

revision = "338"
down_revision = "337"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
