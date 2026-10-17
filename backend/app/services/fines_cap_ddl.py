"""The DDL behind the Fines session cap and per-fine notes (migration 342), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``fine_settings.max_per_session``
    The most one player can be fined in a single session (one date) in this
    squad. NULL means no limit, which is every squad that already exists.

``fine_entries.note``
    A line of detail about one fine ("dropped it at fine leg, 12th over"), shown
    beside the reason on the report. Optional.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE fine_settings ADD COLUMN IF NOT EXISTS max_per_session NUMERIC(10,2)",
    "ALTER TABLE fine_entries ADD COLUMN IF NOT EXISTS note TEXT",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE fine_entries DROP COLUMN IF EXISTS note",
    "ALTER TABLE fine_settings DROP COLUMN IF EXISTS max_per_session",
]
