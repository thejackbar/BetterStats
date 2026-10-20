"""DDL for the club's "amalgamate winter and summer seasons" switch (migration 331).

THE ONE COPY. Both alembic (versions/331_amalgamate_seasons.py) and the lifespan
mirror in main.py run this same list, in this order. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

``organisations.amalgamate_seasons`` is the club's choice, off for everybody.
Off means a club's Winter 2026 and Summer 2026/27 are two seasons everywhere
(filters, season tables, season-picked totals). On restores the year-only rule:
one season per calendar year. Nothing is stored per season; the kind is read
from the season's name (services/season_kind.py).
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS amalgamate_seasons",
]
