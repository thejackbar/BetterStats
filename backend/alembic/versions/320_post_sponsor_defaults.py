"""The sponsors a club's posts start with, pinned to a team or grade.

`organisations.post_sponsor_defaults` holds only what a club pinned. Which
sponsors a post gets is derived on read (team, then grade, then the club's
Social posts spot, then its top sponsor).

Runs services/post_sponsors_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 320
Revises: 319
"""
from alembic import op

from app.services.post_sponsors_ddl import STATEMENTS, DOWNGRADE

revision = "320"
down_revision = "319"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
