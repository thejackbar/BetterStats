"""Locked-down club users: user_access

A Club Admin account can be locked to one module. Defined once in
services/access_ddl.py, which main.py's lifespan mirror and the football
schema mirror also run. Every statement is idempotent.

Revision ID: 344
Revises: 343
"""
from alembic import op

from app.services.access_ddl import STATEMENTS, DOWNGRADE

revision = "344"
down_revision = "343"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
