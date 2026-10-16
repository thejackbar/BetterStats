"""The DDL behind locking a confirmed side and the selection audit trail (migration 334), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``fixtures.locked_at`` / ``locked_by``
    A confirmed side can be locked. NULL is unlocked, which is every existing
    fixture, so nothing changes until a selector confirms or locks one. A locked
    side refuses edits (the XI, its draft, a call-up that would pull a player
    out of it) until somebody with the selection capability unlocks it.

``selection_events``
    The audit trail: one row per change to a side (confirmed, locked, unlocked,
    called up out of, restored), who did it, and the players before and after.
    It is a record of what people decided, so rows are never deleted by code;
    they go with the fixture. ``detail`` carries ``before`` / ``after`` lineups
    as ``[{player_id, name, batting_order, is_captain, is_wicket_keeper}]`` and
    the ``added`` / ``removed`` names, so the history reads without a join.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS locked_at TIMESTAMPTZ",
    "ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS locked_by UUID REFERENCES users(id) ON DELETE SET NULL",
    """CREATE TABLE IF NOT EXISTS selection_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        fixture_id UUID NOT NULL REFERENCES fixtures(id) ON DELETE CASCADE,
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        user_name TEXT,
        action TEXT NOT NULL,
        detail JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_selection_events_fixture ON selection_events (fixture_id, created_at DESC)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS selection_events",
    "ALTER TABLE fixtures DROP COLUMN IF EXISTS locked_by",
    "ALTER TABLE fixtures DROP COLUMN IF EXISTS locked_at",
]
