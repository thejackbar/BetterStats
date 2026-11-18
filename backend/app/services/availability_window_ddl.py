"""The DDL behind how far ahead players may answer for themselves (migration 390), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``organisations.availability_weeks_available``
    How many weeks ahead a player may say Available (or Maybe) on their own page.
    NULL is no limit, which is every existing club.

``organisations.availability_weeks_unavailable``
    How many weeks ahead a player may say Unavailable. NULL is no limit. A club
    can keep this longer than the Available window, so players flag holidays early
    but only commit to playing for the next few weeks.

Both only bind the player's own page. Selectors can record any answer on any date,
and answers already stored outside a window stay as they are.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS availability_weeks_available INTEGER",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS availability_weeks_unavailable INTEGER",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS availability_weeks_unavailable",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS availability_weeks_available",
]
