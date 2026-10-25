"""When a running Fantasy round's scores were last checked against the scorecards (migration 361).

`fantasy_rounds.live_checked_at` is stamped by the live pass (`services/fantasy_live`) each time it
has read the round's games and brought the provisional points in line, whether or not anything
moved. The member Live screen and the admin Rounds table show it, so "nothing has changed" can be
told apart from "nothing has been looked at". It is not a score and nothing derives from it.

ONE copy of the DDL: alembic's 361 and main.py's lifespan mirror both run STATEMENTS.
Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE fantasy_rounds ADD COLUMN IF NOT EXISTS live_checked_at TIMESTAMPTZ",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE fantasy_rounds DROP COLUMN IF EXISTS live_checked_at",
]
