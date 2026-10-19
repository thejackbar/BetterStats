"""The DDL behind an honour board's "only awards named" filter (migration 343), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``club_honour_boards.source_achievement``
    When a board auto-lists a category, optionally only the awards with this
    exact name (case and surrounding spaces ignored), for example
    "A Grade Cap Number" inside Club Award. NULL means every award in the
    category, which is every board that already exists.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE club_honour_boards ADD COLUMN IF NOT EXISTS source_achievement TEXT",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE club_honour_boards DROP COLUMN IF EXISTS source_achievement",
]
