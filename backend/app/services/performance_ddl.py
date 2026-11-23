"""Performance Tracker: one row per round an association workspace tracks.

`data` is the round as the tracker page holds it: each competition's name, pasted
link and what that link pulled (results, performers, ladder, next round), and the
workspace's own notes. The pulled figures are a snapshot, so a round reopens as
it was read; the live round is read again only when someone presses Pull.

A round is archived (`archived_at`), never deleted: it holds what people typed.

The tracker began as a podcast run sheet (migration 395, `podcast_episodes`).
Its rows are copied across once, by id, and that table is left as it was.

`ca_club_careers` (migration 397) keeps each Cricket Australia club's career
totals, per player, as Cricket Australia publishes them (all grades, every
season the club holds on play.cricket.com.au). It is public data keyed by the
club's own id, shared by every workspace, refreshed in the background at most
weekly (services/performance_season.py). It is a cache: a row can be refetched
at any time, and nobody types into it.

One copy: alembic migrations 396 and 397 and main.py's lifespan run these lists.
Every statement is idempotent.
"""

STATEMENTS_396 = [
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

STATEMENTS_397 = [
    """
    CREATE TABLE IF NOT EXISTS ca_club_careers (
        ca_org_id TEXT PRIMARY KEY,
        name TEXT,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        players INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'new',
        error TEXT,
        started_at TIMESTAMPTZ,
        fetched_at TIMESTAMPTZ
    )
    """,
]

STATEMENTS = STATEMENTS_396 + STATEMENTS_397

DOWNGRADE_396 = [
    "DROP TABLE IF EXISTS performance_rounds",
]
DOWNGRADE_397 = [
    "DROP TABLE IF EXISTS ca_club_careers",
]
DOWNGRADE = DOWNGRADE_397 + DOWNGRADE_396
