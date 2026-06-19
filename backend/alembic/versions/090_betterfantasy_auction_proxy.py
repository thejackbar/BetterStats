"""BetterFantasyCricket — auction proxy bids (lot_max_bids on fantasy_drafts)

Turns the auction into eBay-style proxy bidding: every bid is a max, the system
bids up to it on the manager's behalf, and the displayed price is the runner-up's
max plus the increment (capped at the leader's max). The per-lot maxes live in a
JSONB map keyed by manager id, cleared when the lot settles. Full design:
docs/betterfantasycricket.md.

Additive and idempotent (ADD COLUMN IF NOT EXISTS) so it can't collide with the
main.py lifespan mirror.

Revision ID: 090
Revises: 089
Create Date: 2026-06-19

"""
from alembic import op


revision = '090'
down_revision = '089'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE fantasy_drafts ADD COLUMN IF NOT EXISTS lot_max_bids JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE fantasy_drafts DROP COLUMN IF EXISTS lot_max_bids")
