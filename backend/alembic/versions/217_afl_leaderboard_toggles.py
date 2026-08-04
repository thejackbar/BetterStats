"""AFL: per-club toggles for the optional public leaderboard categories.

Games and Goals stay always-on; Best on Ground and the two vote-tally
leaderboards (Club/Competition Best & Fairest) are now a club's own call.
Default true (opt-out), so nothing already-visible disappears until a club
actively turns one off.

Revision ID: 217
Revises: 216
Create Date: 2026-08-05
"""
from alembic import op

revision = "217"
down_revision = "216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "public_show_bog_leaderboard BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "public_show_club_bf_leaderboard BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "public_show_comp_bf_leaderboard BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS public_show_comp_bf_leaderboard")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS public_show_club_bf_leaderboard")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS public_show_bog_leaderboard")
