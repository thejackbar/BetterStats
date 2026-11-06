"""Club teaser snapshots: the club's accent colour and light or dark, from its logo

Defined once in services/club_teaser_ddl.THEME_STATEMENTS, which main.py's lifespan
mirror also runs (it runs the whole STATEMENTS list on every boot).

Revision ID: 384
Revises: 383
"""
from alembic import op

from app.services.club_teaser_ddl import THEME_STATEMENTS, THEME_DOWNGRADE

revision = "384"
down_revision = "383"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in THEME_STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in THEME_DOWNGRADE:
        op.execute(statement)
