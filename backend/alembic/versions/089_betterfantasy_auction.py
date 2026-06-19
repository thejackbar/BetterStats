"""BetterFantasyCricket — auction draft (live lot + nomination state on fantasy_drafts)

Snake drafts pre-create every pick slot, so the draft engine only needed the
order and a walking pointer. An auction can't know who wins a lot ahead of time,
so it carries the *live* state on the draft row: whose turn it is to nominate
(`nomination_index`), the player currently up for auction and its running high
bid / high bidder / nominator (`lot_*`), the anti-snipe deadline, and whether the
lot was auto-nominated by the clock. Each settled lot is appended to
`fantasy_draft_picks` (manager = winner, `bid_amount` = price), reusing the snake
draft's finalisation into squads. Per-manager budget is derived from those picks
(no extra table). Full design: docs/betterfantasycricket.md.

Additive and idempotent (ADD COLUMN IF NOT EXISTS) so it can't collide with the
main.py lifespan mirror, which adds the same columns defensively at boot.

Revision ID: 089
Revises: 088
Create Date: 2026-06-18

"""
from alembic import op


revision = '089'
down_revision = '088'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE fantasy_drafts
            ADD COLUMN IF NOT EXISTS nomination_index INTEGER NOT NULL DEFAULT 0,
            ADD COLUMN IF NOT EXISTS lot_player_id UUID REFERENCES players(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS lot_high_bid NUMERIC(8,1),
            ADD COLUMN IF NOT EXISTS lot_high_bidder_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS lot_nominator_id UUID REFERENCES fantasy_managers(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS lot_deadline TIMESTAMPTZ,
            ADD COLUMN IF NOT EXISTS lot_auto BOOLEAN NOT NULL DEFAULT false
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE fantasy_drafts
            DROP COLUMN IF EXISTS lot_auto,
            DROP COLUMN IF EXISTS lot_deadline,
            DROP COLUMN IF EXISTS lot_nominator_id,
            DROP COLUMN IF EXISTS lot_high_bidder_id,
            DROP COLUMN IF EXISTS lot_high_bid,
            DROP COLUMN IF EXISTS lot_player_id,
            DROP COLUMN IF EXISTS nomination_index
    """)
