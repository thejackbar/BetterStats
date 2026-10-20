"""DDL for the club switch that shows a player their squad on the self-service
availability page (migration 325).

THE ONE COPY. Both alembic (versions/325_availability_show_squad.py) and the
lifespan mirror in main.py run this same list. Every statement is idempotent,
because the lifespan re-runs the whole list on every boot.

One column: ``organisations.availability_show_squad``. Off by default: some
clubs do not want players to know which squad they have been put in, so nothing
about a player's squad is shown to them until the club turns it on.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
    "availability_show_squad BOOLEAN NOT NULL DEFAULT false",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS availability_show_squad",
]
