"""Junior Rotation: saved groups, typed player names and per-game batting and fielding rounds

Defined once in services/rotation_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 381
Revises: 380
"""
from alembic import op

from app.services.rotation_ddl import STATEMENTS, DOWNGRADE

revision = "381"
down_revision = "380"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
