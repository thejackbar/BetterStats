"""The index behind every "what has this club renamed this grade to" lookup (migration 358), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``ix_grades_name_override``
    A grade's display name is the club's own override for that grade NAME, so the
    lookup is ``grades.name = <name> AND display_name_override IS NOT NULL``
    (joined to the club's seasons). ``grades`` had no index on ``name``, so each
    lookup read every grade on the platform. Records, the Leaderboard grade grid,
    StatLab, competition stats and the grade pickers all run it once per row, and a
    picked grade runs a second one inside the filter: a long-history club's
    Partnerships and Records page took 32 to 46 seconds.

    The index is partial. Only a few grades carry an override, so it stays tiny and
    costs a write only when an override is set. Every caller's predicate states
    ``display_name_override IS NOT NULL`` (or ``= :grade_name``, which implies it), so
    Postgres can use it. Nothing about any result changes.
"""

STATEMENTS: list[str] = [
    "CREATE INDEX IF NOT EXISTS ix_grades_name_override "
    "ON grades (name) WHERE display_name_override IS NOT NULL",
]

DOWNGRADE: list[str] = [
    "DROP INDEX IF EXISTS ix_grades_name_override",
]
