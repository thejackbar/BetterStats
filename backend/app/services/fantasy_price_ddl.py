"""Fantasy player prices that move with performances (migration 326).

`fantasy_pool_players.price_locked` marks a price an admin typed in by hand. The
price movement (`services/fantasy_pricing.recompute_prices`) never touches a
locked price; an explicit "recalculate prices" hands it back.

ONE copy of the DDL, per the vote_medal_ddl rule: alembic's 326 and main.py's
lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

# Until now nothing moved a price except an admin (a hand edit) or a rebuild that
# kept the live price, so a price that differs from its starting price was set on
# purpose and managers bought at it. The block adds the column and locks those
# players ONCE (when the column is first created), then does nothing on every
# later boot; a plain UPDATE here would lock every player the movement had moved.
STATEMENTS = [
    """
    DO $$
    BEGIN
        IF NOT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = current_schema()
              AND table_name = 'fantasy_pool_players' AND column_name = 'price_locked'
        ) THEN
            ALTER TABLE fantasy_pool_players ADD COLUMN price_locked BOOLEAN NOT NULL DEFAULT false;
            UPDATE fantasy_pool_players SET price_locked = true WHERE current_price <> base_price;
        END IF;
    END $$
    """,
]

# Drops only the column this migration added.
DOWNGRADE = [
    "ALTER TABLE fantasy_pool_players DROP COLUMN IF EXISTS price_locked",
]
