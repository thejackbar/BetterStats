"""DDL for the sponsor a club puts on its player cards (migration 367).

THE ONE COPY. Both alembic (versions/367_card_sponsors.py) and the lifespan
mirror in main.py run this same list. Every statement is idempotent, because the
lifespan re-runs the whole list on every boot.

One column: ``organisations.card_sponsors`` holds the sponsor a club picked for
each card surface, {"share_card": "<uuid>", "player_cards": "<uuid>"}. NULL, or
a missing key, means the club has not picked and the card shows its top sponsor
that has a logo, as it did before this column. Which sponsor a card shows is
DERIVED on read (services/card_sponsors.py), so a deleted sponsor or a removed
logo is never stale here.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS card_sponsors JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS card_sponsors",
]
