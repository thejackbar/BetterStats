"""A player's third photograph, the action shot, and which shot fills the hero position (migration 374).

A player now has three photographs, each doing its own job:

* the profile photo (`photo_*`): the square headshot that reads at 44px on a roster row;
* the hero photo (`hero_photo_*`, migration 274): the tall photo that fills the big slot on a card, a share card and a
  match-day post. It was labelled "Action shot" in the admin until this migration; the stored bytes and routes are untouched;
* the action shot (`action_photo_*`, new): the player mid-shot, for the same hero position when the club would rather
  show that than the hero photo.

`players.hero_source` is the club's per-player choice of which of the last two fills the hero position on a card, a
share card and a post: NULL means automatic (the hero photo, else the action shot), `hero` and `action` pin one. A pinned
shot the player does not have falls back to the other, then to the profile photo, so a choice can never leave a hole.

ONE copy of the DDL: alembic's 374 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS action_photo_data BYTEA",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS action_photo_mime TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS action_photo_url TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS hero_source TEXT",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE players DROP COLUMN IF EXISTS hero_source",
    "ALTER TABLE players DROP COLUMN IF EXISTS action_photo_url",
    "ALTER TABLE players DROP COLUMN IF EXISTS action_photo_mime",
    "ALTER TABLE players DROP COLUMN IF EXISTS action_photo_data",
]
