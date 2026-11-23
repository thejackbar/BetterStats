"""Podcast run sheets: one row per episode a club or association workspace plans.

`data` is the run sheet as the editor holds it (competition links, what each link
pulled, the hosts' notes, the Sunday night checklist). The pulled figures are a
snapshot the hosts talk from, kept so an episode reopens as it was recorded; the
live round is re-read only when someone presses Pull again.

An episode is archived (`archived_at`), never deleted: it holds what people typed.

One copy: alembic migration 395 and main.py's lifespan both run STATEMENTS. Every
statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS podcast_episodes (
        id UUID PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        episode_no INTEGER,
        recording_date DATE,
        round_label TEXT,
        data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by UUID,
        archived_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_podcast_episodes_org "
    "ON podcast_episodes (organisation_id, archived_at)",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS podcast_episodes",
]
