"""Teamwear ordering: campaigns, member orders, triage, payments, export, receive and pack

Runs services/teamwear_ddl.STATEMENTS, which the main.py lifespan also runs. Every statement is
idempotent. Adds `merch_square_connections.can_take_payments` (a connection made before this
release asked Square for read scopes only).

Revision ID: 402
Revises: 401
"""
from alembic import op

from app.services.teamwear_ddl import DOWNGRADE_402, STATEMENTS

revision = "402"
down_revision = "401"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_402:
        op.execute(statement)
