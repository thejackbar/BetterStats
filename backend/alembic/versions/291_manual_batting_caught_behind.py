"""Let a manual scorecard say a batter was caught behind.

``batting_innings.caught_behind`` has existed since migration 075, and
``manual_bowler_wickets`` got its own in 093 — but ``manual_batting_innings``
never did, so ``v_effective_batting_innings``'s manual branch has always
emitted ``NULL::boolean``. Every reader treats NULL as "a plain catch", which
is the right answer for a card that does not record it and the wrong one for a
card that does.

Shoalwater Bay's own scoring program does record it: their Cricket Statistics
for Windows files carry a distinct dismissal code for a keeper's catch, which
the club confirmed. Without this column that fact is read out of a
thirty-year-old file, carried all the way through the conversion, and then
dropped on the floor at the moment it is written down.

Nothing changes for a club that has never set it. The column is nullable with
no default, so every manual innings already stored reads NULL exactly as it
did when the view hardcoded one.

Revision ID: 291
Revises: 290
"""
from alembic import op

revision = '291'
down_revision = '290'
branch_labels = None
depends_on = None


# Keep this DDL byte-identical to the defensive copy in app/main.py's lifespan.
# The two are re-run on every boot and a drift between them is a schema
# mismatch nothing would report — see migration 290's own verify() note.
VIEW = """
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
        caught_behind
    FROM manual_batting_innings
"""

STATEMENTS = [
    "ALTER TABLE manual_batting_innings ADD COLUMN IF NOT EXISTS caught_behind BOOLEAN",
    VIEW,
]


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # Put the hardcoded NULL back FIRST: the view reads the column, so dropping
    # it while the view still selects it fails outright.
    op.execute("""
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
    """)
    op.execute("ALTER TABLE manual_batting_innings DROP COLUMN IF EXISTS caught_behind")
