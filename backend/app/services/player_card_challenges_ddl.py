"""Player Cards, challenges (migration 380): sets with a goal and a reward, in the manner of a squad building challenge.

* `club_card_challenges`: a challenge a club (an admin) publishes to every player. Two kinds:
    - `exchange`: hand in cards that meet the rules (11 Rare cards, 11 Common cards, a squad rated 70 or more...) and they are spent.
    - `collection`: hold a list of cards (the players of a premiership side, every Legendary...) and they are kept.
  Either one pays a reward pack when it is completed. `rules` and `reward` are validated JSON (services/player_card_challenges.py).
* `player_card_challenge_runs`: what a player completed and when. For an exchange it is the record of the cards that were spent.
  The completion of a code-defined set ("Every century at the club") is recorded here too, keyed `set:<set key>`. A reward pack is
  granted once per run, so this table is also what stops a challenge paying twice.
* `player_card_my_sets`: a player's own private set, a list of cards they have decided to collect. It pays nothing and nobody else
  can see it.

ONE copy of the DDL: alembic's 380 and main.py's lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS club_card_challenges (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        title TEXT NOT NULL,
        blurb TEXT,
        rules JSONB NOT NULL DEFAULT '{}'::jsonb,
        reward JSONB NOT NULL DEFAULT '{}'::jsonb,
        max_completions INTEGER NOT NULL DEFAULT 1,
        starts_on DATE,
        ends_on DATE,
        active BOOLEAN NOT NULL DEFAULT TRUE,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_challenges_org ON club_card_challenges (organisation_id, active, sort_order)",
    """
    CREATE TABLE IF NOT EXISTS player_card_challenge_runs (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        challenge_key TEXT NOT NULL,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        n INTEGER NOT NULL DEFAULT 1,
        submitted JSONB NOT NULL DEFAULT '[]'::jsonb,
        completed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS ux_card_challenge_runs ON player_card_challenge_runs (player_id, challenge_key, n)",
    """
    CREATE TABLE IF NOT EXISTS player_card_my_sets (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        title TEXT NOT NULL,
        selector JSONB NOT NULL DEFAULT '{}'::jsonb,
        card_keys JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_my_sets_player ON player_card_my_sets (player_id)",
]

# Drops only the three tables this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_my_sets",
    "DROP TABLE IF EXISTS player_card_challenge_runs",
    "DROP TABLE IF EXISTS club_card_challenges",
]
