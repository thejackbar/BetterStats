"""Player Cards, which photo a card shows (migration 376): the club's choice of how many cards get the big photo.

A player has three photos (profile, hero, action). Which one a card shows depends on the card (`player_cards.card_shot`): a plain
card shows the profile photo in a circle, and the bigger the moment the more likely it is to get a full-card photo. This is the
club's setting for how far that goes:

* `top` (the default): special cards, Epic and Legendary cards get the big photo; Common and Rare cards keep the circle.
* `specials`: only special cards get it.
* `all`: every card with a big photo shows it (how cards looked before 376).

ONE copy of the DDL: alembic's 376 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS big_photos TEXT NOT NULL DEFAULT 'top'",
]

# Drops only the column this migration added.
DOWNGRADE = ["ALTER TABLE club_card_settings DROP COLUMN IF EXISTS big_photos"]
