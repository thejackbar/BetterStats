"""The DDL behind a squad covering several teams (migration 336), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``team_sides``
    A squad (``teams``) used to be one team: one grade, one rank. A club that
    keeps one pool of players for its 1st and 2nd XI, another for the 3rds and a
    third for the 4ths to 6ths needs a squad to cover several teams. Each row is
    one TEAM (a grade: "1st XI" plays in this grade) that belongs to the squad.

    * ``grade_key`` is the grade's name with the sponsor suffix off, lowercased
      (``grade_labels.grade_key``). It is matched by name, never by grade id, so
      it keeps working when the season rolls over and CA issues new grade rows.
    * ``position`` is the team's place inside the squad, 0 first. Its XI number
      is the squad's order plus this, so a squad ordered 4 with three teams is the
      4th, 5th and 6th XI. Derived on read, never stored, so changing the squad's
      order moves them all.
    * ``label`` is what the team is called on fixtures and the board. Empty means
      "1st XI" style from its number, or the grade name for an unranked squad.
    * A grade can belong to one squad only (unique per club): a fixture has one
      home.

    A squad with no rows here is the old single-grade squad (``teams.grade_id``),
    unchanged.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS team_sides (
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        grade_key TEXT NOT NULL,
        grade_name TEXT NOT NULL,
        label TEXT,
        position INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (team_id, grade_key)
    )""",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_team_sides_org_grade ON team_sides (organisation_id, grade_key)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS team_sides",
]
