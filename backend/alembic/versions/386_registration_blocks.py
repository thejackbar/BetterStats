"""Club block list: registration_blocks.

A registered club, a Cricket Australia club id, a club name, an email address or
an email domain that BetterCricket will not serve. Nothing is ever deleted from
it; lifting a block stamps `lifted_at`.

Runs services/registration_block_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 386
Revises: 385
"""
from alembic import op

from app.services.registration_block_ddl import STATEMENTS, DOWNGRADE

revision = "386"
down_revision = "385"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
