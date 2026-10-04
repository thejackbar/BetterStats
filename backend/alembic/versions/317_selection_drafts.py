"""Autosaved draft of the selection board's side.

`selection_drafts` holds the XI a selector is still building, one row per
fixture, apart from `fixture_lineups` (the confirmed XI). Leaving the board
mid-pick no longer loses the work; Confirm writes the real lineup and clears
the draft.

Runs services/selection_draft_ddl.STATEMENTS, the same list main.py's
lifespan runs. Every statement is idempotent.

Revision ID: 317
Revises: 316
"""
from alembic import op

from app.services.selection_draft_ddl import STATEMENTS, DOWNGRADE

revision = "317"
down_revision = "316"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
