"""Linked clubs: club_links

A Super Admin links two or more clubs; a Club Admin of any club in the group
can then switch which of them they are working in. Defined once in
services/club_link_ddl.py, which main.py's lifespan mirror and the football
schema mirror also run.

Revision ID: 322
Revises: 321
"""
from alembic import op

from app.services.club_link_ddl import STATEMENTS, DOWNGRADE

revision = "322"
down_revision = "321"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
