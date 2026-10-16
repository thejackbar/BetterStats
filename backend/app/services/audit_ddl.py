"""The DDL behind the club-wide audit trail (migration 339), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``audit_events``
    One row per change to a player in selection, availability or squads: who did
    it (a user, or the player themselves through their link), when, which player,
    which squad or game, and a plain sentence for the list. Names are stored as
    they were at the time so the trail reads the same after a rename or a merge,
    and ``player_id`` / ``team_id`` / ``fixture_id`` are plain ids with no foreign
    key, so the record outlives the thing it describes. Code never deletes rows.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS audit_events (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        user_id UUID,
        user_name TEXT,
        via TEXT NOT NULL DEFAULT 'admin',
        area TEXT NOT NULL,
        action TEXT NOT NULL,
        player_id UUID,
        player_name TEXT,
        team_id UUID,
        team_name TEXT,
        fixture_id UUID,
        fixture_label TEXT,
        summary TEXT NOT NULL DEFAULT '',
        detail JSONB NOT NULL DEFAULT '{}'::jsonb
    )""",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_org_time ON audit_events (organisation_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_audit_events_player ON audit_events (organisation_id, player_id, created_at DESC)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS audit_events",
]
