"""DDL for a team's own number of players (migration 330), in ONE place.

Alembic (versions/330_team_size.py) and ``main.py``'s lifespan both run
``STATEMENTS``. The lifespan re-runs the list on every boot, so every statement
is idempotent.

One column: ``teams.team_size``. NULL means "use the club's default"; 0 means
no limit. Nothing is backfilled: every existing team keeps following the club.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS team_size INTEGER",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE teams DROP COLUMN IF EXISTS team_size",
]
