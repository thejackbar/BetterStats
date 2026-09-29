"""Super-admin messages shown on the club admin dashboard

`admin_broadcasts` holds each message and its audience and lifetime rules;
`admin_broadcast_receipts` records who has seen or dismissed it. Both are
defined once in services/admin_broadcast_ddl.py, which main.py's lifespan
mirror also runs.

Revision ID: 312
Revises: 311
"""
from alembic import op

from app.services.admin_broadcast_ddl import STATEMENTS, DOWNGRADE

revision = "312"
down_revision = "311"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
