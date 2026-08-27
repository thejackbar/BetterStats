"""
DDL for the Super Admin instructional video library (migration 280).

THE ONE COPY. Both alembic (versions/280_instructional_videos.py) and the
lifespan mirror in main.py run this same list, in this order, per the
vote_medal_ddl rule — two hand-kept copies of a schema drift the first time
one is edited. Every statement is idempotent, because the lifespan re-runs the
whole list on every boot.

The video bytes live in Postgres rather than on a volume, the same call
committee_documents and player photos already make: the upload volume is not
guaranteed to persist, and a video an admin uploaded must not vanish with the
container. Reads slice the column with SQL substring() so serving a range of a
large file never loads the whole blob into memory.
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
        video_data         BYTEA,
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

# Dropped newest-first by the migration's downgrade.
DOWNGRADE_STATEMENTS: list[str] = [
    "DROP INDEX IF EXISTS ix_instructional_videos_order",
    "DROP INDEX IF EXISTS uq_instructional_videos_slug",
    "DROP TABLE IF EXISTS instructional_videos",
]
