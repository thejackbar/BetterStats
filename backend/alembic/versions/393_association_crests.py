"""Association workspace crest library: `association_crests`.

Each club's crest, fetched once from Cricket Australia with its plain background
taken off, kept per workspace so every post reuses it. Runs
services/association_crest_ddl.STATEMENTS, the same list main.py's lifespan runs.
Every statement is idempotent.

Revision ID: 393
Revises: 392
"""
from alembic import op

from app.services.association_crest_ddl import STATEMENTS, DOWNGRADE

revision = "393"
down_revision = "392"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
