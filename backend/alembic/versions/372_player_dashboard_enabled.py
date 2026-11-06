"""A Player Dashboard on/off switch that does not need BetterSelect.

`organisations.player_dashboard_enabled` (nullable; NULL keeps the old behaviour).

Runs services/player_dashboard_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 372
Revises: 371
"""
from alembic import op

from app.services.player_dashboard_ddl import STATEMENTS, DOWNGRADE

revision = "372"
down_revision = "371"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
