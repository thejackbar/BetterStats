"""Podcast run sheets: the `podcast_episodes` table.

Runs services/podcast_ddl.STATEMENTS; main.py's lifespan runs the same list.
Every statement is idempotent.

Revision ID: 395
Revises: 394
"""
from alembic import op

from app.services.podcast_ddl import STATEMENTS, DOWNGRADE

revision = "395"
down_revision = "394"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
