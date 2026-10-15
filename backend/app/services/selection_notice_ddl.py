"""The DDL behind "send the confirmed side to the captain / the players" (migration 329), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the
two copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``selection_notices``
    One row per send: which fixture, who it went to (``captain`` or a
    ``player``), what the confirmed side looked like when it went
    (``fingerprint``: the ordered ids plus captain and keeper) and whether it
    got out. It is what lets the automatic send on Confirm skip a side the
    captain already has, and lets the board say "sent to Sam at 4:12pm".
    A notice is a record of something the club did, so it is never deleted by
    code; the fixture's own delete cascades it away.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS selection_notices (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        player_id UUID REFERENCES players(id) ON DELETE SET NULL,
        recipient_name TEXT,
        recipient_email TEXT,
        fingerprint TEXT,
        status TEXT NOT NULL,
        detail TEXT,
        automatic BOOLEAN NOT NULL DEFAULT FALSE,
        sent_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_selection_notices_fixture ON selection_notices (fixture_id, created_at DESC)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS selection_notices",
]
