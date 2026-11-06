"""Player Cards, packs a club creates (migration 374): a quality for any pack, and a record of the packs a club hands out by hand.

* `player_card_packs.quality`: which of the quality levels (`standard` ... `legendary`, see `player_card_pack_kinds.QUALITIES`) a pack is
  drawn at. NULL = the pack's own kind decides (every pack made before this).
* `club_card_event_packs.quality`: the same, for a scheduled pack. Defaults to `special`, which is the odds scheduled packs have always had.
* `club_card_pack_gifts`: one row for each time an admin creates packs for players (a name, a quality, how many each, who). The packs
  themselves are `player_card_packs` rows with source `custom` and ref `<gift id>:<n>`. The row is what the admin sees afterwards, and its
  id doubles as the guard against a double click granting twice.

ONE copy of the DDL: alembic's 374 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE player_card_packs ADD COLUMN IF NOT EXISTS quality TEXT",
    "ALTER TABLE club_card_event_packs ADD COLUMN IF NOT EXISTS quality TEXT NOT NULL DEFAULT 'special'",
    """
    CREATE TABLE IF NOT EXISTS club_card_pack_gifts (
        id UUID PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        quality TEXT NOT NULL,
        qty INTEGER NOT NULL DEFAULT 1,
        audience TEXT NOT NULL DEFAULT 'all',
        players INTEGER NOT NULL DEFAULT 0,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_pack_gifts_org ON club_card_pack_gifts (organisation_id, created_at DESC)",
]

# Drops only what this migration added. (The packs and events tables are earlier migrations'.)
DOWNGRADE = [
    "DROP TABLE IF EXISTS club_card_pack_gifts",
    "ALTER TABLE club_card_event_packs DROP COLUMN IF EXISTS quality",
    "ALTER TABLE player_card_packs DROP COLUMN IF EXISTS quality",
]
