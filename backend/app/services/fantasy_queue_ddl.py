"""Fantasy round lock time and transfers queued behind a locked round (migration 327).

* `fantasy_rounds.lock_manual` marks a lock time an admin set by hand, so the nightly
  round refresh (`fantasy_engine.generate_rounds`) leaves it alone.
* `fantasy_queued_transfers` holds a transfer a manager made after the round locked.
  It waits on `after_round_id`; when that round is scored it is carried out at the
  prices after settlement (`services/fantasy_queue`). The squad's picks are not
  touched until then, so the locked round is scored with the XI that was locked.
  Both player columns are on `merge_carry.CARRIED`.

ONE copy of the DDL, per the vote_medal_ddl rule: alembic's 327 and main.py's
lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE fantasy_rounds ADD COLUMN IF NOT EXISTS lock_manual BOOLEAN NOT NULL DEFAULT false",
    """
    CREATE TABLE IF NOT EXISTS fantasy_queued_transfers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        fantasy_season_id UUID NOT NULL REFERENCES fantasy_seasons(id) ON DELETE CASCADE,
        squad_id UUID NOT NULL REFERENCES fantasy_squads(id) ON DELETE CASCADE,
        after_round_id UUID NOT NULL REFERENCES fantasy_rounds(id) ON DELETE CASCADE,
        out_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        in_player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        status TEXT NOT NULL DEFAULT 'pending',
        reason TEXT,
        sell_value NUMERIC(8,1),
        buy_price NUMERIC(8,1),
        hit INTEGER NOT NULL DEFAULT 0,
        free_used BOOLEAN NOT NULL DEFAULT false,
        out_purchase_price NUMERIC(8,1),
        out_added_round INTEGER,
        out_was_captain BOOLEAN NOT NULL DEFAULT false,
        out_was_vice BOOLEAN NOT NULL DEFAULT false,
        applied_round_number INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        applied_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_fantasy_queued_transfers_squad ON fantasy_queued_transfers(squad_id, status)",
    "CREATE INDEX IF NOT EXISTS ix_fantasy_queued_transfers_round ON fantasy_queued_transfers(after_round_id, status)",
]

# Drops only what this migration added.
DOWNGRADE = [
    "DROP TABLE IF EXISTS fantasy_queued_transfers",
    "ALTER TABLE fantasy_rounds DROP COLUMN IF EXISTS lock_manual",
]
