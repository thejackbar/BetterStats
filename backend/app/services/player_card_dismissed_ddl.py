"""Player Cards: suggested swaps a player has dismissed (migration 386).

* `player_card_dismissed_swaps`: one row per suggested swap a player waved away: the other player, the card the
  asker would give and the card they would get. A dismissal only hides that exact pairing, for the player who made it.
  The other player still sees their own side, and a different pairing (a new card either way) can still be suggested.
  Undo deletes the row, because nobody else decided anything about it.

Every player column is on `merge_carry.CARRIED`. ONE copy of the DDL: alembic's 386 and main.py's lifespan mirror both
run STATEMENTS, and every statement is idempotent.
"""

_NIL = "'00000000-0000-0000-0000-000000000000'::uuid"

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_dismissed_swaps (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        other_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        give_subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        give_special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        want_subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        want_special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    f"CREATE UNIQUE INDEX IF NOT EXISTS ux_card_dismissed_swaps ON player_card_dismissed_swaps "
    f"(player_id, other_player_id, give_subject_player_id, COALESCE(give_special_id, {_NIL}), "
    f"want_subject_player_id, COALESCE(want_special_id, {_NIL}))",
    "CREATE INDEX IF NOT EXISTS ix_card_dismissed_swaps_player ON player_card_dismissed_swaps (player_id)",
]

# Drops only what this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_dismissed_swaps",
]
