"""A fixture records which of its squad's teams plays it.

`fixtures.side_key` (grade key, NULL = work it out from the grade). Existing
fixtures behave as before.

Runs services/fixture_side_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 337
Revises: 336
"""
from alembic import op

from app.services.fixture_side_ddl import STATEMENTS, DOWNGRADE

revision = "337"
down_revision = "336"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
