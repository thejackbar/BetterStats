"""A club can switch off the "Maybe" availability answer.

`organisations.availability_allow_maybe` (default true). Existing answers are left alone.

Runs services/availability_maybe_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 340
Revises: 339
"""
from alembic import op

from app.services.availability_maybe_ddl import STATEMENTS, DOWNGRADE

revision = "340"
down_revision = "339"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
