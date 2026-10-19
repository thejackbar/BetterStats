"""The ONE copy of migration 330's DDL, run by alembic and by the lifespan mirror.

Same one-copy rule as services/milestone_scheme_ddl.py. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

Two parts:

* ``organisations.milestone_matches_step`` and ``milestone_catches_step``: the
  club-wide matches and catches increments, beside the runs and wickets ones
  migration 321 added. NULL means the club has not chosen (every 50).
* ``milestone_grade_schemes``: one row per (club, grade) that has increments of
  its own. A NULL step in a row means "follow the club's setting" for that stat.
  ``grade_key`` is ``services/grade_labels.grade_key`` of the grade's canonical
  name (sponsor suffix off, lowercased, folded through the club's grade
  merges), so a grade is one grade across seasons. ``grade_name`` is the
  spelling the club read when it saved, for the screen only.

Read both through services/grade_milestone_schemes.load_book, never directly.
"""

STATEMENTS = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS milestone_matches_step INTEGER",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS milestone_catches_step INTEGER",
    """
    CREATE TABLE IF NOT EXISTS milestone_grade_schemes (
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        grade_key TEXT NOT NULL,
        grade_name TEXT NOT NULL,
        runs_step INTEGER,
        wickets_step INTEGER,
        matches_step INTEGER,
        catches_step INTEGER,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (organisation_id, grade_key)
    )
    """,
]

# Drops only what this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS milestone_grade_schemes",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS milestone_matches_step",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS milestone_catches_step",
]
