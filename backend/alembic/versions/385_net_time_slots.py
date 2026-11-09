"""Time-slot nets: a session can run as a grid of nets by time slots.

`net_sessions.mode` / `.slot_plan` and `net_attendance.net_key` / `.slot_index` /
`.slot_manual`, plus a unique index so a cell holds one person. Existing sessions
read `manual` and behave as before.

Runs services/net_slots_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 385
Revises: 384
"""
from alembic import op

from app.services.net_slots_ddl import STATEMENTS, DOWNGRADE

revision = "385"
down_revision = "384"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
