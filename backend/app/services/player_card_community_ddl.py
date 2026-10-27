"""Player Cards, the community side (migration 369): the showcase, the opt-ins for the collectors board and the club feed, and the
club's switches for sets, showcase, board and feed.

* `player_card_showcase`: up to six cards a player pins up (`slot` is their order; it is not unique, so a merge cannot collide on it), shown to the club on their board entry and on Home. Only a
  card the player holds can be pinned (checked when it is saved and again when it is read, so a card swapped away drops off).
* `player_card_prefs.board_opt_in` (default OFF: a player is on the collectors board only if they say so) and `.feed_hidden` (default
  OFF: the club feed names people unless they opt out).
* `club_card_settings.sets_enabled`, `.showcase_enabled`, `.board_enabled`, `.feed_enabled`: the club's switches, all on to begin with.

Sets, the board and the feed are derived on read and store nothing. Every player column is on `merge_carry.CARRIED`. ONE copy of the DDL:
alembic's 369 and main.py's lifespan mirror both run STATEMENTS, and every statement is idempotent.
"""

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_showcase (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        slot SMALLINT NOT NULL,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_showcase_player ON player_card_showcase (player_id, slot)",
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_card_showcase_card ON player_card_showcase (player_id, subject_player_id, COALESCE(special_id, {_NIL}))",
    "ALTER TABLE player_card_prefs ADD COLUMN IF NOT EXISTS board_opt_in BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE player_card_prefs ADD COLUMN IF NOT EXISTS feed_hidden BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS sets_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS showcase_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS board_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS feed_enabled BOOLEAN NOT NULL DEFAULT TRUE",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS feed_enabled",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS board_enabled",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS showcase_enabled",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS sets_enabled",
    "ALTER TABLE player_card_prefs DROP COLUMN IF EXISTS feed_hidden",
    "ALTER TABLE player_card_prefs DROP COLUMN IF EXISTS board_opt_in",
    "DROP TABLE IF EXISTS player_card_showcase",
]
