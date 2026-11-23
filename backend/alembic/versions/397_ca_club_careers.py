"""Performance Tracker: `ca_club_careers`, each Cricket Australia club's career
totals per player, for career milestones.

Runs services/performance_ddl.STATEMENTS_397; main.py's lifespan runs the whole
STATEMENTS list. Every statement is idempotent.

Revision ID: 397
Revises: 396
"""
from alembic import op

from app.services.performance_ddl import STATEMENTS_397, DOWNGRADE_397

revision = "397"
down_revision = "396"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS_397:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_397:
        op.execute(stmt)
