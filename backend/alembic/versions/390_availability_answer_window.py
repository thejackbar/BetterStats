"""A club can limit how many weeks ahead players answer for themselves.

`organisations.availability_weeks_available` and `availability_weeks_unavailable`
(both nullable, NULL is no limit). Existing answers are left alone.

Runs services/availability_window_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 390
Revises: 389
"""
from alembic import op

from app.services.availability_window_ddl import STATEMENTS, DOWNGRADE

revision = "390"
down_revision = "389"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
