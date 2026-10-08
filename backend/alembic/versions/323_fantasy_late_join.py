"""Fantasy late joiners: fantasy_squads.catchup_points

A manager who registers after the season has started begins level with the
lowest team on the ladder. The starting points are kept in their own column so
the round-by-round recompute of a squad's total does not wipe them. Defined once
in services/fantasy_late_join_ddl.py, which main.py's lifespan mirror also runs.

Revision ID: 323
Revises: 322
"""
from alembic import op

from app.services.fantasy_late_join_ddl import STATEMENTS, DOWNGRADE

revision = "323"
down_revision = "322"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
