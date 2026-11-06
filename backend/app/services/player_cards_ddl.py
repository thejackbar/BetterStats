"""Player Cards: collectable cards, packs and the club's card settings (migration 363).

Four club-scoped tables and one settings table. A card is never stored as a row of its own: a
player's regular card is derived from their figures on read, and what a person OWNS is a row in
`player_card_copies` (one row per copy, so a duplicate is just a second row). Special cards are the
exception: a special card commemorates one event, and the event is a row in `player_special_cards`.

* `player_card_packs`: a pack somebody has earned. A grant only ever ADDS a row (the unique key
  makes a re-run a no-op), so a figure corrected downwards later never takes a pack away.
* `player_card_copies`: a card a player owns. `subject_player_id` is who is on the card,
  `special_id` is set for a special card. The player's own card is not a row (it is always theirs).
* `player_special_cards`: one commemorative card per event (a century, a five-for, a 100th game).
* `player_card_hidden`: a player the club has taken out of the card pool.
* `club_card_settings`: the club's switches (one row per club, created on first save).

Every player-keyed table is on `merge_carry.CARRIED`, so a player merge moves a collection and
never deletes it.

ONE copy of the DDL: alembic's 363 and main.py's lifespan mirror both run STATEMENTS. The lifespan
re-runs every statement on every boot, so each one is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS club_card_settings (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT TRUE,
        include_juniors BOOLEAN NOT NULL DEFAULT FALSE,
        weekly_packs INTEGER NOT NULL DEFAULT 1,
        timezone TEXT,
        launched_at TIMESTAMPTZ,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_special_cards (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        event_key TEXT NOT NULL,
        game_id UUID,
        occurred_on DATE,
        title TEXT NOT NULL,
        detail JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_special_cards_event ON player_special_cards (organisation_id, event_key)",
    "CREATE INDEX IF NOT EXISTS ix_special_cards_player ON player_special_cards (player_id)",
    """
    CREATE TABLE IF NOT EXISTS player_card_packs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        source TEXT NOT NULL,
        ref_key TEXT NOT NULL,
        granted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        opened_at TIMESTAMPTZ
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_packs_grant ON player_card_packs (player_id, source, ref_key)",
    "CREATE INDEX IF NOT EXISTS ix_card_packs_player_open ON player_card_packs (player_id) WHERE opened_at IS NULL",
    """
    CREATE TABLE IF NOT EXISTS player_card_copies (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        owner_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        pack_id UUID REFERENCES player_card_packs(id) ON DELETE SET NULL,
        source TEXT NOT NULL,
        obtained_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_copies_owner ON player_card_copies (owner_player_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_copies_gift ON player_card_copies (owner_player_id, special_id) WHERE source = 'gift'",
    """
    CREATE TABLE IF NOT EXISTS player_card_hidden (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        hidden_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        hidden_by TEXT
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_hidden_player ON player_card_hidden (organisation_id, player_id)",
]

# Drops only what this migration added, children before parents.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_copies",
    "DROP TABLE IF EXISTS player_card_packs",
    "DROP TABLE IF EXISTS player_special_cards",
    "DROP TABLE IF EXISTS player_card_hidden",
    "DROP TABLE IF EXISTS club_card_settings",
]
