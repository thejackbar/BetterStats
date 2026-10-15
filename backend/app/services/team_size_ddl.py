"""DDL for a team's own side size (migration 332).

THE ONE COPY. Both alembic (versions/332_team_default_size.py) and the
lifespan mirror in main.py run this same list. Every statement is idempotent,
because the lifespan re-runs the whole list on every boot.

``teams.default_team_size`` is the number of players in that team's XI
(0 = no limit). NULL means the team has no size of its own and follows the
club's ``organisations.default_team_size``.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS default_team_size INTEGER",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE teams DROP COLUMN IF EXISTS default_team_size",
]
