"""Player Cards: the pile (migration 388).

* `player_card_pile`: a card a player has flagged as a spare they are happy to swap. Everyone in the club can see a player's pile in
  the Market, by name. A row is only a flag: whether the card counts as in the pile is derived on read, from the copies the player
  holds right now (a pile card needs a spare, a copy beyond the one they keep), so a card swapped away drops out of the pile by
  itself and comes back if the player gets another spare. A flag is the player's own, so un-flagging deletes the row.

Every player column is on `merge_carry.CARRIED`. ONE copy of the DDL: alembic's 388 and main.py's lifespan mirror both run
STATEMENTS, and every statement is idempotent.
"""

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_pile (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_card_pile ON player_card_pile (player_id, subject_player_id, COALESCE(special_id, {_NIL}))",
    "CREATE INDEX IF NOT EXISTS ix_card_pile_org ON player_card_pile (organisation_id)",
]

# Drops only what this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_pile",
]
