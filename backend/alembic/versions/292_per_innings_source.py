"""Every effective view applies the season's source, not just two of them

287 let a club say CricketStatz is the record for a season it also syncs, and
applied it in `v_effective_games` and `v_effective_player_season_stats`. The
six PER-INNINGS views were never filtered, so for a superseded season both the
synced innings and the imported innings were present — reported live as a
record board listing the same 270 twice and a career at 14,806 runs.

Re-runs services/superseded_ddl.STATEMENTS, which 287 and 290 also run. Every
statement is idempotent.

Revision ID: 292
Revises: 291
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "292"
down_revision = "291"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # 287 owns the column and the views; undoing it removes these too.
    pass
