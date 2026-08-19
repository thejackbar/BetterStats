"""Hiding a player, and the two BetterSelect flags a club sets by hand.

``players.is_public``
    Whether this player appears on the club's PUBLIC site. Defaults true, so
    nothing is hidden by an upgrade. The case that asked for it is a junior
    who does not want to be findable: their stats stay in the club's own
    admin surfaces (the club still needs them for selection, fees and
    reports) and drop out of the public roster, search, profile page,
    leaderboards and records. Same shape and same default as
    ``grades.is_public`` (migration 123), and read through the same
    ``user_can_view_org_private`` escape, so a signed-in club admin still
    sees their whole club.

``players.is_financial_override`` / ``players.trained_override``
    BetterSelect's "non-financial" and "attended training" filters. Both are
    DERIVED by default — owing comes from BetterFees' own balance
    (``services/fees.owing_player_ids``), training from Net Manager
    attendance — and both are nullable here because NULL means "no override,
    use what the data says". A club that runs neither module gets an
    ordinary tick box; a club that runs them can still correct one player
    without the derivation being wrong for everyone.

Revision ID: 265
Revises: 264
"""
from alembic import op

revision = "265"
down_revision = "264"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS "
        "is_public BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS is_financial_override BOOLEAN"
    )
    op.execute(
        "ALTER TABLE players ADD COLUMN IF NOT EXISTS trained_override BOOLEAN"
    )
    # The public roster reads "this club's visible players" on every page
    # load; a partial index keeps that cheap without paying for the (much
    # larger) visible set.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_players_org_hidden "
        "ON players (organisation_id) WHERE is_public IS FALSE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_players_org_hidden")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS trained_override")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS is_financial_override")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS is_public")
