"""The DDL behind switching off the "Maybe" availability answer (migration 340), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``organisations.availability_allow_maybe``
    On by default, which is every existing club. A club that turns it off can
    only record Available or Unavailable (or no response): the admin screens and
    the player's own page stop offering Maybe, and the server refuses it. Answers
    already recorded as Maybe stay as they are and still show.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS availability_allow_maybe BOOLEAN NOT NULL DEFAULT TRUE",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS availability_allow_maybe",
]
