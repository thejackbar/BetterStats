"""Player Cards, more packs (migration 370): packs for a day, for an achievement and for events the club schedules; the
club's starting-cards setting; and the defaults for alerts and the board.

* `player_card_packs.label`: the name of a pack that has a name of its own (a scheduled event, "Australia v South Africa, First Test").
* `club_card_event_packs`: days a club has scheduled a pack for (a Test match, a club day): from `starts_on` to `ends_on`, one pack
  a day (`per_day`) or one for the whole run.
* `club_card_settings.event_packs_enabled`: the club's switch for holiday, birthday, surprise and Match Day packs.
  `.starter_gifts`: `minimal` (a player's debut card and their latest milestone card, and their own card) or `all`.
* `player_card_prefs.board_hidden`: a player who leaves the collectors board (everyone is on it until they do; this replaces
  `board_opt_in`, which is no longer read). The alert columns now default to OFF: nobody is emailed until they ask.

ONE copy of the DDL: alembic's 370 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent. (Alembic's 370
also switches the alert columns off for rows made under the old default; that is data, runs once, and is not in this list.)
"""

STATEMENTS = [
    "ALTER TABLE player_card_packs ADD COLUMN IF NOT EXISTS label TEXT",
    """
    CREATE TABLE IF NOT EXISTS club_card_event_packs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        starts_on DATE NOT NULL,
        ends_on DATE NOT NULL,
        per_day BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_event_packs_org ON club_card_event_packs (organisation_id, starts_on)",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS event_packs_enabled BOOLEAN NOT NULL DEFAULT TRUE",
    "ALTER TABLE club_card_settings ADD COLUMN IF NOT EXISTS starter_gifts TEXT NOT NULL DEFAULT 'minimal'",
    "ALTER TABLE player_card_prefs ADD COLUMN IF NOT EXISTS board_hidden BOOLEAN NOT NULL DEFAULT FALSE",
    "ALTER TABLE player_card_prefs ALTER COLUMN alert_swaps SET DEFAULT FALSE",
    "ALTER TABLE player_card_prefs ALTER COLUMN alert_wants SET DEFAULT FALSE",
]

# Drops only what this migration added. (The two defaults go back to on.)
DOWNGRADE = [
    "ALTER TABLE player_card_prefs ALTER COLUMN alert_wants SET DEFAULT TRUE",
    "ALTER TABLE player_card_prefs ALTER COLUMN alert_swaps SET DEFAULT TRUE",
    "ALTER TABLE player_card_prefs DROP COLUMN IF EXISTS board_hidden",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS starter_gifts",
    "ALTER TABLE club_card_settings DROP COLUMN IF EXISTS event_packs_enabled",
    "DROP TABLE IF EXISTS club_card_event_packs",
    "ALTER TABLE player_card_packs DROP COLUMN IF EXISTS label",
]
