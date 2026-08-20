"""Where a club's engagement score came from, cached per club.

``marketing_clubs.engagement_sources``
    ``{source_key: points}`` — the same rollup ``twenty_sync._engagement()``
    already computes on its way to the score, kept beside the score itself
    (``engagement_score``/``engagement_tier``, which have been cached here for
    the same reason since migration 192). The CRM's pipeline board holds
    hundreds of deals at once, and re-running a per-club scan of
    ``usage_events`` for every card so the board could be filtered by "came to
    us through Meta ads" is not a query anyone should pay for on a page load.

    A key with 0 points means the club really did that — clicked an ad, opened
    an email — but the score is currently made of something else (a direct
    enquiry pins it, or the registration floor beat the activity tally). The
    filter asks "has this club come to us this way", which that has to answer
    yes to; the chart draws only the keys carrying points.

    NULL means "not scored since this shipped", not "no sources". Every
    ``_engagement()`` call fills it in, so it self-heals as the nightly
    refresh, a BetterComms send, or opening the club's own detail card comes
    around; ``python -m app.scripts.recalc_engagement`` fills the whole table
    at once.

The GIN index is what makes ``engagement_sources ? 'meta_ads'`` cheap enough
to run across the directory rather than only over a loaded board.

Revision ID: 270
Revises: 269
"""
from alembic import op

revision = "270"
down_revision = "269"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS engagement_sources JSONB")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_marketing_clubs_engagement_sources "
        "ON marketing_clubs USING GIN (engagement_sources)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_marketing_clubs_engagement_sources")
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS engagement_sources")
