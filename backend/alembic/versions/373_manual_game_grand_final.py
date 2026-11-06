"""A hand-entered or imported game can be marked as the grand final.

`manual_games.is_grand_final` (NOT NULL, default FALSE). The automatic premierships read it
for a manual game the way they read `games.round_name` for a synced one.

Runs services/manual_grand_final_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 373
Revises: 372
"""
from alembic import op

from app.services.manual_grand_final_ddl import STATEMENTS, DOWNGRADE

revision = "373"
down_revision = "372"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
