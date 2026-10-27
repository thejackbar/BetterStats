"""Player Cards, the social side (migration 368): a wish list, spares players are open to swap, each player's alert
settings, the log of alerts sent, counter offers and a note on a swap request.

* `player_card_wants`: a card a player is after. Private to the player. Add only in spirit: removing a want deletes the row,
  because nobody else decided anything about it.
* `player_card_open_offers`: a card the holder has said they are open to swapping, so the holder is shown how many players
  want it (a count, never names).
* `player_card_prefs`: one row per player, made on first save. An absent row means the defaults (alerts on).
* `player_card_alerts`: every alert considered, so the club can see what went where. One live row per (player, kind, ref):
  the partial unique index is what stops a second email for the same card until it has been cleared.
* `player_card_swaps.parent_swap_id` and `.note`: a counter offer points at the request it answers; a note travels with a
  request. `club_card_settings.alerts_enabled` is the club's switch for all alert email.

Every player column is on `merge_carry.CARRIED`. ONE copy of the DDL: alembic's 368 and main.py's lifespan mirror both run
STATEMENTS, and every statement is idempotent.
"""

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_wants (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_card_wants ON player_card_wants (player_id, subject_player_id, COALESCE(special_id, {_NIL}))",
    "CREATE INDEX IF NOT EXISTS ix_card_wants_org ON player_card_wants (organisation_id, subject_player_id)",
    """
    CREATE TABLE IF NOT EXISTS player_card_open_offers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_card_open_offers ON player_card_open_offers (player_id, subject_player_id, COALESCE(special_id, {_NIL}))",
    """
    CREATE TABLE IF NOT EXISTS player_card_prefs (
        player_id UUID PRIMARY KEY REFERENCES players(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        alert_swaps BOOLEAN NOT NULL DEFAULT TRUE,
        alert_wants BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS player_card_alerts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        ref_key TEXT NOT NULL,
        status TEXT NOT NULL,
        detail TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        cleared_at TIMESTAMPTZ
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_alerts_live ON player_card_alerts (player_id, kind, ref_key) "
    "WHERE cleared_at IS NULL AND status IN ('sent', 'skipped')",
    "ALTER TABLE player_card_swaps ADD COLUMN IF NOT EXISTS parent_swap_id UUID REFERENCES player_card_swaps(id)",
    "ALTER TABLE player_card_swaps ADD COLUMN IF NOT EXISTS note TEXT",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS alerts_enabled BOOLEAN NOT NULL DEFAULT TRUE",
]

# Drops only what this migration added.
DOWNGRADE = [
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS alerts_enabled",
    "ALTER TABLE player_card_swaps DROP COLUMN IF EXISTS note",
    "ALTER TABLE player_card_swaps DROP COLUMN IF EXISTS parent_swap_id",
    "DROP TABLE IF EXISTS player_card_alerts",
    "DROP TABLE IF EXISTS player_card_prefs",
    "DROP TABLE IF EXISTS player_card_open_offers",
    "DROP TABLE IF EXISTS player_card_wants",
]
