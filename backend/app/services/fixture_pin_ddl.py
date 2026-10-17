"""The DDL behind "this fixture's squad was picked by hand" (migration 338), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``fixtures.team_pinned``
    True once someone chose the squad on a synced fixture by hand. Sync fixes a
    synced fixture that sits on a squad which does not play its grade (a name
    match that guessed wrong); it never moves a pinned one. False for every
    existing fixture, so the next Sync tidies the old guesses.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS team_pinned BOOLEAN NOT NULL DEFAULT FALSE",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE fixtures DROP COLUMN IF EXISTS team_pinned",
]
