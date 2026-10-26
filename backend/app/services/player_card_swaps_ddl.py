"""Player Cards: swap requests between two players of a club (migration 364).

One row per request: who offers (`from_player_id`), who is asked (`to_player_id`), the card offered
(`give_*`) and the card wanted (`want_*`). A card is named by its subject player and, for a special
card, its special card id. A request is never deleted: it ends as accepted, declined, cancelled or
(read from its age, not stored) expired, so a club can see what was agreed.

Every player column is on `merge_carry.CARRIED`, so a player merge moves the requests with the person.

ONE copy of the DDL: alembic's 364 and main.py's lifespan mirror both run STATEMENTS. Every
statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_swaps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        from_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        to_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        give_subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        give_special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        want_subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        want_special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_swaps_to ON player_card_swaps (to_player_id) WHERE status = 'pending'",
    "CREATE INDEX IF NOT EXISTS ix_card_swaps_from ON player_card_swaps (from_player_id) WHERE status = 'pending'",
]

# Drops only what this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_swaps",
]
