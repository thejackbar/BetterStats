"""Show a player the grades they actually played, when the default would hide them all.

``organisations.stats_auto_show_played_grades`` (default TRUE) covers the case
migration 228's junior split creates: a player who has only ever played junior
cricket opens their own profile on a page of zeroes, because the club's default
leaves junior out. That reads as a broken page, not as a filter working.

With this on, a profile whose default scope would exclude every category the
player has actually turned out in adds those categories back for that player,
and says so on the page. It only ever affects the DEFAULT — someone who switches
Juniors off by hand still gets what they asked for, or the toggle would appear
not to work.

Default TRUE because the alternative is a blank profile, and a club that wants
the stricter reading can switch it off. NULL is impossible (NOT NULL + default),
so no club needs to set anything on upgrade.

Revision ID: 229
Revises: 228
"""
from alembic import op

revision = "229"
down_revision = "228"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "stats_auto_show_played_grades BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE organisations DROP COLUMN IF EXISTS stats_auto_show_played_grades"
    )
