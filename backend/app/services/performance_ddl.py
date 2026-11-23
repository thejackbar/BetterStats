"""Performance Tracker: one row per round an association workspace tracks.

`data` is the round as the tracker page holds it: each competition's name, pasted
link and what that link pulled (results, performers, ladder, next round), and the
workspace's own notes. The pulled figures are a snapshot, so a round reopens as
it was read; the live round is read again only when someone presses Pull.

A round is archived (`archived_at`), never deleted: it holds what people typed.

The tracker began as a podcast run sheet (migration 395, `podcast_episodes`).
Its rows are copied across once, by id, and that table is left as it was.

One copy: alembic migration 396 and main.py's lifespan both run STATEMENTS. Every
statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS performance_rounds (
        id UUID PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        round_label TEXT,
        round_date DATE,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by UUID,
        archived_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_performance_rounds_org "
    "ON performance_rounds (organisation_id, archived_at)",
    """
    DO $$
    BEGIN
        IF to_regclass('public.podcast_episodes') IS NOT NULL THEN
            INSERT INTO performance_rounds
                (id, organisation_id, round_label, round_date, data, created_at, updated_at, updated_by, archived_at)
            SELECT p.id, p.organisation_id, p.round_label, p.recording_date, p.data,
                   p.created_at, p.updated_at, p.updated_by, p.archived_at
            FROM podcast_episodes p
            WHERE NOT EXISTS (SELECT 1 FROM performance_rounds r WHERE r.id = p.id);
        END IF;
    END $$
    """,
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS performance_rounds",
]
