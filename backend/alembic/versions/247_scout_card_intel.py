"""BetterScout — scouting-report attributes + manual intel on a watchlist card

Adds is_opening_batsman/is_wicket_keeper/fielding_position (same shape as
players.is_opening_batsman on the club side) and batting_intel/bowling_intel
JSONB (the exact shape services/scouting_intel.py already validates for
BetterIQ's own player scouting cards, reused rather than re-invented).

Revision ID: 247
Revises: 246
"""
from alembic import op

revision = "247"
down_revision = "246"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS is_opening_batsman BOOLEAN")
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS is_wicket_keeper BOOLEAN")
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS fielding_position TEXT")
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS batting_intel JSONB")
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS bowling_intel JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS is_opening_batsman")
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS is_wicket_keeper")
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS fielding_position")
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS batting_intel")
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS bowling_intel")
