"""A player's own page gets club-chosen modules, and BetterSelect gets Fines.

`organisations.player_dashboard_modules` (JSONB, NULL = the old page), and the
`fine_settings`, `fine_types`, `fine_entries`, `fine_payments` tables. Nothing
existing is changed or backfilled.

Runs services/fines_ddl.STATEMENTS, the same list main.py's lifespan runs. Every
statement is idempotent.

Revision ID: 341
Revises: 340
"""
from alembic import op

from app.services.fines_ddl import STATEMENTS, DOWNGRADE

revision = "341"
down_revision = "340"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
