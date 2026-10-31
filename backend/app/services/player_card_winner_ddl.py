"""Player Cards, Winner Winner packs (migration 383): the club's switch, and the day they start.

* `club_card_settings.winner_packs`: the club's switch for the pack every player who played in a win gets the day after it.
* `club_card_settings.winner_packs_from`: the first day a win can earn one. A club that already uses cards gets the day this
  migration ran, so its history is not paid out at once; a club that starts using cards later gets that day.

ONE copy of the DDL: alembic's 383 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS winner_packs BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS winner_packs_from DATE NOT NULL DEFAULT CURRENT_DATE",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS winner_packs_from",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS winner_packs",
]
