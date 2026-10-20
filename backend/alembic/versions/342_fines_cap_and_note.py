"""Fines: a per-session maximum for a squad, and a note on each fine.

`fine_settings.max_per_session` (NULL = no limit) and `fine_entries.note`.
Nothing existing is changed.

Runs services/fines_cap_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 342
Revises: 341
"""
from alembic import op

from app.services.fines_cap_ddl import STATEMENTS, DOWNGRADE

revision = "342"
down_revision = "341"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
