"""BetterScout — pricing tiers (limits + upgrade messaging only, no Stripe)

scout_orgs.tier: starter | growth | unlimited, default 'starter'. Caps and
enforcement live in services/scout_billing.py + scout_watchlist.py's
ensure_card_on_default_watchlist — a tier is assigned by BetterCricket staff
(scripts/scout_set_tier.py), not self-serve.

Revision ID: 240
Revises: 239
"""
from alembic import op

revision = "240"
down_revision = "239"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'starter'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scout_orgs DROP COLUMN IF EXISTS tier")
