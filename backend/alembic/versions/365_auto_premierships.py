"""Automatic premierships: games.round_name, achievement-to-scorecard link, auto marker, exclusions

Defined once in services/premierships_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 365
Revises: 364
"""
from alembic import op

from app.services.premierships_ddl import STATEMENTS, DOWNGRADE

revision = "365"
down_revision = "364"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
