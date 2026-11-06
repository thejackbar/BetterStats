"""Player Cards, a pack made by hand can be designed and sized as it is made (migration 378).

* `club_card_pack_designs.line`: the few words under a pack's name ("Fresh this week"). NULL = the built-in line for that kind.
* `player_card_packs.size`: how many cards are in THIS pack (NULL = the usual five). A club can make a pack of 3 or of 10.
* `club_card_pack_gifts.size`: the same, as the admin entered it.

A pack made by hand also gets a design of its own, held in `club_card_pack_designs` under the target `gift:<gift id>`; that
needs no new column.

ONE copy of the DDL: alembic's 378 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE club_card_pack_designs ADD COLUMN IF NOT EXISTS line TEXT",
    "ALTER TABLE player_card_packs ADD COLUMN IF NOT EXISTS size INTEGER",
    "ALTER TABLE club_card_pack_gifts ADD COLUMN IF NOT EXISTS size INTEGER NOT NULL DEFAULT 5",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE club_card_pack_gifts DROP COLUMN IF EXISTS size",
    "ALTER TABLE player_card_packs DROP COLUMN IF EXISTS size",
    "ALTER TABLE club_card_pack_designs DROP COLUMN IF EXISTS line",
]
