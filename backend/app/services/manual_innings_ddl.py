"""Per-innings meta for a hand-entered manual game (migration 310).

A hand-typed manual game has nowhere to record three things the photo-upload
path already captures in `extracted_payload`:

  * which side batted an innings (so our BOWLING can be filed in the innings
    the OPPOSITION batted, not lumped into innings 1 alongside our batting —
    the reported case where our own bowlers were drawn as the attack against
    our own batters and their wides/no-balls polluted our batting extras);
  * an innings' extras (byes / leg-byes / wides / no-balls / penalty, or a
    single total) — our batting innings has no bowler rows of ours to derive
    them from, and byes/leg-byes are never a bowler stat anyway;
  * the opposition innings' own total (runs / wickets / overs), since the
    opposition's batters can't be itemised in the hand-entry form (a manual
    batting row FKs to our own players table).

`manual_innings` holds all three, one row per (game, innings_number). It is
purely additive: a game with no rows here behaves exactly as before, and the
photo-upload path is untouched (it still reads `extracted_payload`).

ONE copy of the DDL — alembic's 310 and main.py's lifespan mirror both run
STATEMENTS, per the vote_medal_ddl rule. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS manual_innings (
        id SERIAL PRIMARY KEY,
        manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
        innings_number INTEGER NOT NULL DEFAULT 1,
        batting_side TEXT,
        byes INTEGER,
        leg_byes INTEGER,
        wides INTEGER,
        no_balls INTEGER,
        penalty INTEGER,
        extras_total INTEGER,
        total_runs INTEGER,
        total_wickets INTEGER,
        overs NUMERIC(5, 1),
        CONSTRAINT uq_manual_innings_game_number UNIQUE (manual_game_id, innings_number)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_manual_innings_game ON manual_innings(manual_game_id)",
    # Migration 311: whether the source knew who batted first. NULL means it
    # did (a hand-entered or photo-read card, which is numbered in batting
    # order), so every existing game reads exactly as before. FALSE is a match
    # imported from a scorebook that recorded both innings and never the order
    # they were batted in, where the innings numbers are a convention and the
    # match page must not label them "Innings 1" and "Innings 2" or work out a
    # "won by N wickets" from them.
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS innings_order_known BOOLEAN",
]

DOWNGRADE = [
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS innings_order_known",
    "DROP TABLE IF EXISTS manual_innings",
]

# 311's own downgrade: the column alone. 310 owns the table, and copying 310's
# downgrade here would drop every hand-entered innings over one column.
DOWNGRADE_311 = [
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS innings_order_known",
]
