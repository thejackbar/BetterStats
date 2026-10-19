"""The club-wide audit trail for selection, availability and squads.

`audit_events`: who changed which player, where, and when. Additive; nothing
existing reads it.

Runs services/audit_ddl.STATEMENTS, the same list main.py's lifespan runs. Every
statement is idempotent.

Revision ID: 339
Revises: 338
"""
from alembic import op

from app.services.audit_ddl import STATEMENTS, DOWNGRADE

revision = "339"
down_revision = "338"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
