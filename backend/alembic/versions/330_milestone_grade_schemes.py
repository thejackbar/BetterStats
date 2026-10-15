"""Milestone increments per grade, and club-wide matches and catches steps

A club can give one grade (A Grade) smaller or larger milestone increments than
the rest of the club, and can type its own step instead of picking a preset.
Nothing changes for a club that does not choose: every new column is NULL and
the new table starts empty.

Runs services/milestone_grade_scheme_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 330
Revises: 329
Create Date: 2026-10-14
"""
from alembic import op

from app.services.milestone_grade_scheme_ddl import DOWNGRADE, STATEMENTS  # noqa: E402

revision = "330"
down_revision = "329"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
