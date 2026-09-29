"""A re-sourced season counts per match, not per season

An overwrite import that supersedes some of a season's Cricket Australia
matches used to step the WHOLE season's CA summary aside, so every synced match
the file did not hold — a junior grade the old program never tracked, a fixture
the other club synced first — dropped out of the season and career totals while
every filtered read (which uses the per-innings views) kept them. That is how a
player's "Men's" figure came to read HIGHER than their "All".

v_effective_player_season_stats now carries an 'api_scorecard' branch: in a
re-sourced season, a synced game with no preferred imported twin is rolled up
from Cricket Australia's own scorecard rows, and the import's rollup counts only
the matches it holds. The season is the union of both sources, counted once,
decided per match — the rule the per-innings views already keep.

Re-runs services/superseded_ddl.STATEMENTS, which 287, 290, 292, 293 and 303
also run. Every statement is idempotent.

Revision ID: 309
Revises: 308
"""
from alembic import op

from app.services.superseded_ddl import STATEMENTS

revision = "309"
down_revision = "308"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # 287 owns the views; undoing it (superseded_ddl.DOWNGRADE) puts the
    # pre-pairing definitions back.
    pass
