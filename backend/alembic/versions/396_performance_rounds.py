"""Performance Tracker: the `performance_rounds` table, with the podcast run sheet's
rows (migration 395) copied across.

Runs services/performance_ddl.STATEMENTS_396; main.py's lifespan runs the whole STATEMENTS list.
Every statement is idempotent.

Revision ID: 396
Revises: 395
"""
from alembic import op

from app.services.performance_ddl import STATEMENTS_396 as STATEMENTS, DOWNGRADE_396 as DOWNGRADE

revision = "396"
down_revision = "395"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
