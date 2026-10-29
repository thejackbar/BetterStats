"""Player Cards: swap requests between two players of a club (migration 364).

One row per request: who offers (`from_player_id`), who is asked (`to_player_id`), the card offered
(`give_*`) and the card wanted (`want_*`). A card is named by its subject player and, for a special
card, its special card id. A request is never deleted: it ends as accepted, declined, cancelled or
(read from its age, not stored) expired, so a club can see what was agreed.

Every player column is on `merge_carry.CARRIED`, so a player merge moves the requests with the person.

Migration 366 makes a request many cards each way: `player_card_swap_items` holds the cards on each side
(`side` give or want, with a quantity), and the single `give_*` / `want_*` columns above become optional (a
request made before 366 is copied into items once and keeps its old columns; a newer one leaves them empty).

ONE copy of the DDL: alembic's 364 runs BASE_STATEMENTS, 366 runs ITEM_STATEMENTS, and main.py's lifespan
mirror (and the test harnesses) run STATEMENTS, which is both. Every statement is idempotent.
"""

BASE_STATEMENTS = [
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

ITEM_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS player_card_swap_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        swap_id UUID NOT NULL REFERENCES player_card_swaps(id) ON DELETE CASCADE,
        side TEXT NOT NULL,
        subject_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        special_id UUID REFERENCES player_special_cards(id) ON DELETE CASCADE,
        qty INTEGER NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_swap_items_swap ON player_card_swap_items (swap_id)",
    # A request made before 366 carried one card each way in its own columns: copy each across once.
    """
    INSERT INTO player_card_swap_items (organisation_id, swap_id, side, subject_player_id, special_id)
    SELECT s.organisation_id, s.id, 'give', s.give_subject_player_id, s.give_special_id FROM player_card_swaps s
     WHERE s.give_subject_player_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM player_card_swap_items i WHERE i.swap_id = s.id AND i.side = 'give')
    """,
    """
    INSERT INTO player_card_swap_items (organisation_id, swap_id, side, subject_player_id, special_id)
    SELECT s.organisation_id, s.id, 'want', s.want_subject_player_id, s.want_special_id FROM player_card_swaps s
     WHERE s.want_subject_player_id IS NOT NULL
       AND NOT EXISTS (SELECT 1 FROM player_card_swap_items i WHERE i.swap_id = s.id AND i.side = 'want')
    """,
    "ALTER TABLE player_card_swaps ALTER COLUMN give_subject_player_id DROP NOT NULL",
    "ALTER TABLE player_card_swaps ALTER COLUMN want_subject_player_id DROP NOT NULL",
]

STATEMENTS = BASE_STATEMENTS + ITEM_STATEMENTS

# Each drops only what its own migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_swaps",
]
ITEM_DOWNGRADE = [
    "DROP TABLE IF EXISTS player_card_swap_items",
]
