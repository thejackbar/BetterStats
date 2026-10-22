"""An index for the grade display-name lookup, so a long-history club's Records page stops scanning every grade.

`grades` had no index on `name`. The lookup "has the club renamed this grade" is
`name = X AND display_name_override IS NOT NULL`, run once per row by Records,
the Leaderboard grade grid, StatLab and competition stats, and again inside a
picked-grade filter. Each run read every grade on the platform. A partial index
on the few grades that carry an override fixes all of them without changing a
result.

Runs services/grade_name_index_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 358
Revises: 357
"""
from alembic import op

from app.services.grade_name_index_ddl import STATEMENTS, DOWNGRADE

revision = "358"
down_revision = "357"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
