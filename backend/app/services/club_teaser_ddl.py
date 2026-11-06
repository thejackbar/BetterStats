"""The DDL behind club teaser snapshots (migration 314), in ONE place.

alembic and ``main.py``'s lifespan both run this list, in this order, so they
cannot drift (the ``vote_medal_ddl`` rule). Every statement is idempotent.

A snapshot is a marketing artefact for a club that is NOT yet a customer: one
JSON document per Club Directory row, built from a handful of Cricket
Australia season-aggregate and ladder calls. It deliberately owns no
``organisations`` / ``players`` / ``games`` rows.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS club_teaser_snapshots (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        marketing_club_id UUID NOT NULL REFERENCES marketing_clubs(id) ON DELETE CASCADE,
        org_guid TEXT NOT NULL,
        token TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        snapshot JSONB,
        data_hash TEXT,
        version INTEGER NOT NULL DEFAULT 0,
        season_year INTEGER,
        season_start DATE,
        api_calls INTEGER NOT NULL DEFAULT 0,
        attempts INTEGER NOT NULL DEFAULT 0,
        last_error TEXT,
        pulled_at TIMESTAMPTZ,
        changed_at TIMESTAMPTZ,
        next_pull_at TIMESTAMPTZ,
        image_version INTEGER,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_teaser_club "
    "ON club_teaser_snapshots(marketing_club_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_teaser_token "
    "ON club_teaser_snapshots(token)",
    "CREATE INDEX IF NOT EXISTS ix_club_teaser_due "
    "ON club_teaser_snapshots(next_pull_at)",
]

# Migration 384: the club's look on its season page (accent colour and light or
# dark, read from its logo). Its own column, not part of the snapshot, so a
# theme change never moves the snapshot's content hash and never marks a
# picture out of date.
THEME_STATEMENTS = [
    "ALTER TABLE club_teaser_snapshots ADD COLUMN IF NOT EXISTS theme JSONB",
]
STATEMENTS = STATEMENTS + THEME_STATEMENTS

DOWNGRADE = [
    "DROP TABLE IF EXISTS club_teaser_snapshots",
]
THEME_DOWNGRADE = [
    "ALTER TABLE club_teaser_snapshots DROP COLUMN IF EXISTS theme",
]
