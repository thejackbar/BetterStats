"""Player Cards: the Market (migration 387).

* `player_card_prefs.wants_hidden`: a player who keeps their wish list out of the Market. Everyone's list is visible to the
  club until they switch it off in Settings (the same opt-out shape as `board_hidden` and `feed_hidden`). A hidden list is
  still counted in the "N players want this card" numbers, and still drives a suggested swap between the two players
  involved; it is never listed by name in the Market.

No new table, so nothing new for `merge_carry`. ONE copy of the DDL: alembic's 387 and main.py's lifespan mirror both run
STATEMENTS, and every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE player_card_prefs ADD COLUMN IF NOT EXISTS wants_hidden BOOLEAN NOT NULL DEFAULT FALSE",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE player_card_prefs DROP COLUMN IF EXISTS wants_hidden",
]
