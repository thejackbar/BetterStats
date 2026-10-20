"""A club's own Honour Board order.

`organisations.honour_board_layout` holds only what a club changed: the order
of the groups, the roles inside each group, and how the people under a role are
sorted. NULL means the standard order.

Runs services/honour_layout_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 324
Revises: 323
"""
from alembic import op

from app.services.honour_layout_ddl import STATEMENTS, DOWNGRADE

revision = "324"
down_revision = "323"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
