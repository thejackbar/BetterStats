"""An undo log for the partnership backfill.

`partnership_backfill_log`: one row per game the backfill wrote to, holding the ids of the
partnership and fall-of-wicket rows it inserted, so a club that tries it can be rolled back
exactly. No foreign key to `games`.

Runs services/partnership_backfill_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 359
Revises: 358
"""
from alembic import op

from app.services.partnership_backfill_ddl import STATEMENTS, DOWNGRADE

revision = "359"
down_revision = "358"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
