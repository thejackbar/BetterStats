"""The DDL behind marking a dormant player "no longer dormant" (migration 348), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``players.dormancy_cleared_on``
    The day a club said "this player is back". NULL (every existing player) means
    nothing was said. See ``services/dormancy.py`` for how it is read: it counts
    as a last-active date for the dormancy test and nothing else, so it lapses by
    itself and the real last-played date is never touched.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS dormancy_cleared_on DATE",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE players DROP COLUMN IF EXISTS dormancy_cleared_on",
]
