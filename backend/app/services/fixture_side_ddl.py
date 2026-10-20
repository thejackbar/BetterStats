"""The DDL behind a fixture's own team choice (migration 337), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``fixtures.side_key``
    Which of the squad's teams ("2nd XI") plays this fixture, as a grade key
    (``grade_labels.grade_key``). NULL = work it out from the fixture's grade, as
    before. A synced fixture's ``grade_id`` is rewritten from Cricket Australia
    on every sync, so a club's own choice of team cannot live there: it lives
    here, and the sync never touches it.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS side_key TEXT",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE fixtures DROP COLUMN IF EXISTS side_key",
]
