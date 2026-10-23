"""The kick-off of a Fantasy round's first match (migration 360).

`fantasy_rounds.first_start` is the club-local wall-clock time ("HH:MM") of the earliest
match on the round's first day, as the Play-Cricket draw gives it. The default lock time
is one hour before it (`fantasy_engine.default_lock_at`). NULL means the draw gave no
time for that day, and the default falls back to 09:00.

ONE copy of the DDL: alembic's 360 and main.py's lifespan mirror both run STATEMENTS.
Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE fantasy_rounds ADD COLUMN IF NOT EXISTS first_start TEXT",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE fantasy_rounds DROP COLUMN IF EXISTS first_start",
]
