"""A historical summary that stops at a season.

`import_batches.through_year` / `through_label` record the last season a club's
own book covers, so the reconciler compares the sheet against the online data
up to that season only and leaves everything after it to the online sources.
NULL keeps today's meaning (the sheet is the whole career).

Runs services/import_through_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 328
Revises: 327
"""
from alembic import op

from app.services.import_through_ddl import STATEMENTS, DOWNGRADE

revision = "328"
down_revision = "327"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
