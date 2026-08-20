"""A net session is run from several devices at once, so the server holds the live state.

``net_sessions.version``
    A counter bumped by every write that changes what the pitch-side screen
    shows — a check-in, a queue re-order, a rotation, the timer starting. The
    live screen polls with the version it last saw and the server hands back a
    two-field "nothing has changed" when they match, so a phone sitting open on
    the boundary costs one small query every couple of seconds rather than the
    whole session payload.

    Bumped as ``version = version + 1`` in SQL, never read-then-write in
    Python: two coaches tapping at the same moment would otherwise compute the
    same next value and one of the two changes would go unnoticed by everyone
    else's poll.

``net_sessions.live_state``
    The batting timer, which used to live only in the browser that started it —
    so a second device showed a stopped clock while the first counted down.
    Holds ``{running, ends_at, remaining_seconds, duration_seconds, turn_seq}``.
    ``ends_at`` is an absolute time, so every device works out the same
    remaining seconds from its own clock corrected against the server's, rather
    than each running its own countdown from whenever it happened to load.

Revision ID: 268
Revises: 267
"""
from alembic import op

revision = "268"
down_revision = "267"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS live_state JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE net_sessions DROP COLUMN IF EXISTS live_state")
    op.execute("ALTER TABLE net_sessions DROP COLUMN IF EXISTS version")
