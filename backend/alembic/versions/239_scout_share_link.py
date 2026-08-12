"""BetterScout — read-only per-card share link

Adds scout_watchlist_cards.share_token: NULL = not shared, a plain unguessable
token (no PIN, no session cookie, unlike every other *_link_token in this app)
because the public read is one record's low-sensitivity cricket data (stats,
tags, notes — never the recruiting-CRM fields on the same card), not a whole
tenant. See services/scout_watchlist.py's create_share_link/get_shared_card.

Revision ID: 239
Revises: 238
"""
from alembic import op

revision = "239"
down_revision = "238"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS share_token TEXT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_scout_watchlist_cards_share_token "
        "ON scout_watchlist_cards(share_token) WHERE share_token IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_scout_watchlist_cards_share_token")
    op.execute("ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS share_token")
