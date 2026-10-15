"""Let a club count winter and summer as one season per year.

`organisations.amalgamate_seasons` is the club's switch, off by default. Off, a
club's "Winter 2026" and "Summer 2026/27" stay separate in every season filter
and season table; on, they are one season per calendar year as they used to be.

Runs services/amalgamate_seasons_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 331
Revises: 330
"""
from alembic import op

from app.services.amalgamate_seasons_ddl import STATEMENTS, DOWNGRADE

revision = "331"
down_revision = "330"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
