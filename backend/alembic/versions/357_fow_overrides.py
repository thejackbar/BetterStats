"""Fall of wickets a club typed from its own scorebook, kept apart from the synced rows.

`fow_overrides`: one row per wicket a club entered for a synced match, with no foreign
key to `games` so a Full Rebuild cannot cascade it away. Re-applied to the game each
time sync stores it, and the partnerships are worked out again from it.

Runs services/fow_override_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 357
Revises: 356
"""
from alembic import op

from app.services.fow_override_ddl import STATEMENTS, DOWNGRADE

revision = "357"
down_revision = "356"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
