"""Lock a confirmed side, and keep an audit trail of changes to it.

`fixtures.locked_at` / `locked_by` (NULL = unlocked, so every existing fixture
behaves as before) and the `selection_events` table.

Runs services/selection_lock_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 334
Revises: 333
"""
from alembic import op

from app.services.selection_lock_ddl import STATEMENTS, DOWNGRADE

revision = "334"
down_revision = "333"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
