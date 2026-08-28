"""
DDL for the Super Admin instructional video library (migration 280).

THE ONE COPY. Both alembic (versions/280_instructional_videos.py) and the
lifespan mirror in main.py run this same list, in this order, per the
vote_medal_ddl rule — two hand-kept copies of a schema drift the first time
one is edited. Every statement is idempotent, because the lifespan re-runs the
whole list on every boot.

WHERE THE BYTES LIVE, AND WHY IT IS SPLIT:

  - The VIDEO is a file on the host media volume (settings.video_storage_dir).
    Only its filename is stored here. Videos are capped at 512MB against
    4-20MB for every other binary in this app, and a bytea that size is
    re-dumped in full by every pg_dump even though the file never changes.
    They are also deliberately OUTSIDE the regular backup — see settings.py.

  - The POSTER stays in Postgres, on purpose. It is ~100KB, so backing it up
    is free, and it means a database restored onto a fresh box still draws a
    recognisable library (titles, descriptions, thumbnails) with only playback
    missing. Splitting a 5MB set of thumbnails out to buy nothing would make
    that failure mode worse for no saving.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS instructional_videos (
        id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        slug               TEXT NOT NULL,
        title              TEXT NOT NULL,
        description        TEXT NOT NULL DEFAULT '',
        module_label       TEXT,
        sort_order         INTEGER NOT NULL DEFAULT 0,
        video_path         TEXT,
        video_mime         TEXT,
        video_size         BIGINT,
        video_filename     TEXT,
        poster_data        BYTEA,
        poster_mime        TEXT,
        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    # A slug is what the public URL is keyed on, so two videos may never share
    # one. The writer resolves a collision by suffixing rather than failing.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_instructional_videos_slug
        ON instructional_videos (slug)
    """,
    # The index the public list reads in its display order. created_at breaks a
    # tie so a reorder that leaves two rows on one number still has a stable
    # order rather than whatever the planner returns.
    """
    CREATE INDEX IF NOT EXISTS ix_instructional_videos_order
        ON instructional_videos (sort_order, created_at)
    """,
]

# Migration 281: how long the video runs.
#
# Its own list because 280 has already been applied in production — a column
# added to STATEMENTS above would never run on a database that has the table.
# Stored as SECONDS rather than the "2m 45s" an admin types, so the display
# format is decided once and the schema.org VideoObject can carry a real
# ISO-8601 duration for search results.
DURATION_STATEMENTS: list[str] = [
    "ALTER TABLE instructional_videos ADD COLUMN IF NOT EXISTS duration_seconds INTEGER",
]

# Dropped newest-first by the migration's downgrade.
DURATION_DOWNGRADE: list[str] = [
    "ALTER TABLE instructional_videos DROP COLUMN IF EXISTS duration_seconds",
]

DOWNGRADE_STATEMENTS: list[str] = [
    "DROP INDEX IF EXISTS ix_instructional_videos_order",
    "DROP INDEX IF EXISTS uq_instructional_videos_slug",
    "DROP TABLE IF EXISTS instructional_videos",
]
