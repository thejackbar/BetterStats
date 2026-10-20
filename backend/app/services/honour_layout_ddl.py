"""DDL for a club's own Honour Board order (migration 324).

THE ONE COPY. Both alembic (versions/324_honour_board_layout.py) and the
lifespan mirror in main.py run this same list. Every statement is idempotent,
because the lifespan re-runs the whole list on every boot.

One column: ``organisations.honour_board_layout`` holds only what a club has
changed, as {"groups": [...], "roles": {group: [...]}, "holders": {group:
{role: {"sort": "newest|oldest|manual", "order": [person keys]}}}}. NULL means
the standard order everywhere (services/honours.py), which is what every club
keeps until an admin saves a change.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS honour_board_layout JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS honour_board_layout",
]
