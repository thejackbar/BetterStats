"""DDL for a team's minimum side size (migration 333).

THE ONE COPY. Both alembic (versions/333_team_min_size.py) and the lifespan
mirror in main.py run this same list. Every statement is idempotent, because
the lifespan re-runs the whole list on every boot.

``teams.min_team_size`` is the fewest players the team may field (a women's or
junior side that needs 8 but may name 12). NULL means no minimum: the side is
complete only when it is full. The size (``default_team_size``) stays the
maximum.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE teams ADD COLUMN IF NOT EXISTS min_team_size INTEGER",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE teams DROP COLUMN IF EXISTS min_team_size",
]
