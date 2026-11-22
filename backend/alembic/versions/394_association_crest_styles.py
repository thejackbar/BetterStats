"""Association crest library: `cut_style` and `clean_version` on `association_crests`.

How each crest's cut-out is made (auto, plain, or on a white die-cut edge) and which
clean-up made it, so an improved clean-up re-cleans kept crests from their stored
original. Runs services/association_crest_ddl.STATEMENTS_394; main.py's lifespan runs
the whole STATEMENTS list. Every statement is idempotent.

Revision ID: 394
Revises: 393
"""
from alembic import op

from app.services.association_crest_ddl import STATEMENTS_394, DOWNGRADE_394

revision = "394"
down_revision = "393"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS_394:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_394:
        op.execute(stmt)
