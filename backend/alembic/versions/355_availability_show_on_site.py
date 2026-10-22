"""A Player Page button on the club's public site, switchable per club.

`organisations.availability_show_on_site` (default true).

Runs services/availability_site_link_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 355
Revises: 354
"""
from alembic import op

from app.services.availability_site_link_ddl import STATEMENTS, DOWNGRADE

revision = "355"
down_revision = "354"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
