"""Player Cards, which photo a card shows (migration 376): the club's choice of how many cards get the big photo.

A player has three photos (profile, hero, action). Which one a card shows depends on the card (`player_cards.card_shot`): a plain
card shows the profile photo in a circle, and the bigger the moment the more likely it is to get a full-card photo. This is the
club's setting for how far that goes:

* `all` (the default, as cards were before 376): every card shows the player's hero photo when they have one, and every special card
  their action shot.
* `top`: only special, Epic and Legendary cards get a big photo; Common and Rare cards keep the circle.
* `specials`: only special cards get one.

Migration 376 first made `top` the default; 380 puts `all` back (the default, and clubs that had only ever had the default).

ONE copy of the DDL: alembic's 376 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS big_photos TEXT NOT NULL DEFAULT 'top'",
    # 380: the default is `all`. (Idempotent. Alembic's 380 also moves the rows still on the old default; that is data, so it is not here.)
    "ALTER TABLE club_card_settings ALTER COLUMN big_photos SET DEFAULT 'all'",
]

# Drops only the column this migration added.
DOWNGRADE = ["ALTER TABLE club_card_settings DROP COLUMN IF EXISTS big_photos"]
