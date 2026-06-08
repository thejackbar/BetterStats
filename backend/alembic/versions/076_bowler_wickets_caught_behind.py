"""Bowling: flag caught-behind on bowler_wickets (caught by the wicketkeeper).

The bowling mirror of migration 075. Lets the "HOW I TAKE WICKETS" donut and the
opponent dossier split a bowler's caught wickets into caught-behind (off the
keeper) vs caught in the field. The keeper signal is the same dagger (†) in the
scorecard's dismissalText that sync already parses to resolve the fielder; we now
persist whether that fielder was the keeper.

NULL = unknown (legacy rows until rebuilt) → readers treat it as a plain catch.
Populated going forward on every sync; back-fill history with
``python -m app.scripts.rebuild_bowler_wickets`` (re-derives the table).

Additive + idempotent. ``bowler_wickets`` is read directly (no effective view),
so no view change is needed.

Revision ID: 076
Revises: 075
Create Date: 2026-06-08

"""
from alembic import op


revision = '076'
down_revision = '075'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE bowler_wickets ADD COLUMN IF NOT EXISTS caught_behind BOOLEAN")


def downgrade() -> None:
    op.execute("ALTER TABLE bowler_wickets DROP COLUMN IF EXISTS caught_behind")
