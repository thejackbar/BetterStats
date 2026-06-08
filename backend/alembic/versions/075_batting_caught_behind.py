"""Batting: flag caught-behind (caught by the wicketkeeper).

CA scorecards mark the keeper with a dagger (``†``) before the catcher's name in
``dismissalText`` (e.g. ``"c †Smith b Jones"``). Sync read that text to resolve
the *fielder* for ``bowler_wickets`` but then stripped the ``†`` and stored a bare
``"c"`` in ``batting_innings.dismissal_type`` — so "caught behind" was
indistinguishable from a regular catch in every batting analytic.

This adds a nullable ``caught_behind`` boolean to ``batting_innings`` (kept off the
``dismissal_type`` string so the existing "count caught" readers are untouched and
keep working), surfaces it through ``v_effective_batting_innings``, and lets the
dismissal-breakdown readers opt in to a distinct "caught behind" slice.

``NULL`` = unknown (legacy rows until back-filled, and manual entries which carry
no keeper signal) → readers treat it as a plain catch. Populated going forward on
every sync, and for history by ``app.scripts.backfill_caught_behind`` or a Full
Rebuild.

Additive + idempotent.

Revision ID: 075
Revises: 074
Create Date: 2026-06-08

"""
from alembic import op


revision = '075'
down_revision = '074'
branch_labels = None
depends_on = None


# Keep this DDL byte-identical to the defensive copy in app/main.py lifespan.
_VIEW_WITH_FLAG = """
    CREATE OR REPLACE VIEW v_effective_batting_innings AS
    SELECT
        id, game_id, player_id, innings_number,
        runs, balls, fours, sixes, strike_rate,
        dismissal_type, not_out, batting_position, did_not_bat,
        'api'::text AS source,
        caught_behind
    FROM batting_innings
    UNION ALL
    SELECT
        id, manual_game_id AS game_id, player_id, innings_number,
        runs, balls, fours, sixes, strike_rate,
        dismissal_type, not_out, batting_position, did_not_bat,
        'manual'::text AS source,
        NULL::boolean AS caught_behind
    FROM manual_batting_innings
"""

_VIEW_WITHOUT_FLAG = """
    CREATE OR REPLACE VIEW v_effective_batting_innings AS
    SELECT
        id, game_id, player_id, innings_number,
        runs, balls, fours, sixes, strike_rate,
        dismissal_type, not_out, batting_position, did_not_bat,
        'api'::text AS source
    FROM batting_innings
    UNION ALL
    SELECT
        id, manual_game_id AS game_id, player_id, innings_number,
        runs, balls, fours, sixes, strike_rate,
        dismissal_type, not_out, batting_position, did_not_bat,
        'manual'::text AS source
    FROM manual_batting_innings
"""


def upgrade() -> None:
    op.execute("ALTER TABLE batting_innings ADD COLUMN IF NOT EXISTS caught_behind BOOLEAN")
    op.execute(_VIEW_WITH_FLAG)


def downgrade() -> None:
    # Recreate the view without the new column first (CREATE OR REPLACE can't
    # drop a column, and the column can't drop while the view references it).
    op.execute("DROP VIEW IF EXISTS v_effective_batting_innings")
    op.execute(_VIEW_WITHOUT_FLAG)
    op.execute("ALTER TABLE batting_innings DROP COLUMN IF EXISTS caught_behind")
