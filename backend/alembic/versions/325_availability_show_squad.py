"""A club's switch for showing players their squad on the availability page.

`organisations.availability_show_squad`, off by default.

Runs services/availability_squad_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 325
Revises: 324
"""
from alembic import op

from app.services.availability_squad_ddl import STATEMENTS, DOWNGRADE

revision = "325"
down_revision = "324"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
