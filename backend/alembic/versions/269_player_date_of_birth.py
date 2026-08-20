"""A player's date of birth, and who is allowed to see the age it works out to.

``players.date_of_birth``
    Plain nullable DATE, entered by hand on the player profile. Nothing
    syncs it — Cricket Australia's feeds carry no birthday, and PlayHQ's
    juniors are name-redacted rather than dated — so this is a club
    recording what it already holds on its own registration forms.

    The AGE is never stored. A stored age is wrong from the day after it is
    written, and a club that fills this in once should not have to maintain
    it; ``services/player_age.age_on`` works it out on every read.

``organisations.select_show_age`` / ``.select_show_age_under``
    Whether BetterSelect shows a player's age beside their name, and for
    whom. Default OFF, so no club starts showing dates of birth to its
    selectors because of an upgrade. ``select_show_age_under`` NULL means
    every player; a number means only players UNDER that age — which is the
    case that asked for this, a coach needing to see at a glance that the
    quick they are about to bowl into the ground is fourteen.

    The limit is applied SERVER-SIDE (services/player_age.visible_age), so a
    club that restricts it to juniors never sends an adult's age to a
    browser at all. A date of birth itself only ever leaves the server on
    the player's own profile payload, which is MANAGE_PLAYERS-gated, and
    never on any public endpoint.

Revision ID: 269
Revises: 268
"""
from alembic import op

revision = "269"
down_revision = "268"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS date_of_birth DATE")
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "select_show_age BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS select_show_age_under INTEGER"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS select_show_age_under")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS select_show_age")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS date_of_birth")
