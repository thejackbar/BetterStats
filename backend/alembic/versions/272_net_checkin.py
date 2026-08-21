"""Someone can turn up to nets and not bat, and players can check themselves in.

``net_attendance.bats``
    Turning up and batting are two different facts, and the queue used to hold
    only one of them. A player who arrives carrying an injury (or to bowl, or to
    keep) is PRESENT — their attendance counts, and the club's report should say
    they were there — but putting them in the batting rotation means a net goes
    empty when their turn comes up. ``bats = false`` keeps the row and takes it
    out of the queue.

``net_attendance.note``
    What they said when they checked themselves in — "sore shoulder", "bowling
    only". Free text, capped in the router. Never required.

``net_attendance.source``
    ``admin`` (a coach ticked them off) or ``self`` (they tapped their own name
    on the check-in screen), mirroring ``player_availability.source``. A club
    looking at a night's register should be able to tell the two apart.

``organisations.net_checkin_token`` / ``.net_checkin_enabled`` / ``.net_checkin_require_pin``
    The check-in screen: one durable per-club link, the same shape as the
    self-service availability link, for the iPad on the door. It resolves to
    whichever session is open TODAY rather than naming one, so the QR taped to
    the wall keeps working every week without anyone reprinting it.

    The token is rotatable and identifies the CLUB only. Whether tapping your
    own name needs the last 4 digits of your mobile is the club's call: a
    supervised iPad in the clubroom is a different risk to a link in a group
    chat, so this one defaults to OFF where the availability link's PIN
    defaults to on.

Revision ID: 272
Revises: 271
"""
from alembic import op

revision = "272"
down_revision = "271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS bats BOOLEAN NOT NULL DEFAULT true")
    op.execute("ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS note TEXT")
    op.execute("ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'admin'")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_token TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_enabled BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS net_checkin_require_pin BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_organisations_net_checkin_token "
        "ON organisations(net_checkin_token) WHERE net_checkin_token IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_organisations_net_checkin_token")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS net_checkin_require_pin")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS net_checkin_enabled")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS net_checkin_token")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS source")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS note")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS bats")
