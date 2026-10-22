"""
DDL for the daily product update (migration 353).

THE ONE COPY. Both alembic (versions/353_product_update_blast.py) and the
lifespan mirror in main.py run this same list, in this order. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

  - ``product_blast_control`` is one row, the Stop switch. It starts STOPPED
    (``paused`` TRUE) and the row is only inserted when absent, so a deploy
    never switches an unreviewed, unattended post on by itself: a super admin
    reads a preview, then presses Start. Re-running the DDL never undoes a Stop
    or a Start.

  - ``product_blasts`` is the log: one row per attempt, whatever happened. The
    ``versions`` array is the changelog versions that attempt looked at, which
    is how the next day knows what has already been covered. A ``failed`` row
    (the changelog or the model was unreachable) does not count as covered, so
    tomorrow tries those items again; ``posted``, ``skipped`` and ``blocked``
    do. ``raw_output`` keeps what the model wrote, so a blocked or retracted
    blast can be looked at afterwards.

Nothing here deletes a blast. Retracting one marks it and removes only the
notifications it raised.
"""

# Added after 353 shipped, so migration 354 runs just these and 353 (on a fresh
# database) runs them as part of STATEMENTS. ``backfilled`` marks a note written
# afterwards for a past day: it shows on What's New and is never notified.
BACKFILL_STATEMENTS: list[str] = [
    "ALTER TABLE product_blasts ADD COLUMN IF NOT EXISTS backfilled BOOLEAN NOT NULL DEFAULT FALSE",
]

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS product_blast_control (
        id          SMALLINT PRIMARY KEY,
        paused      BOOLEAN NOT NULL DEFAULT TRUE,
        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    INSERT INTO product_blast_control (id, paused)
    SELECT 1, TRUE
    WHERE NOT EXISTS (SELECT 1 FROM product_blast_control WHERE id = 1)
    """,
    """
    CREATE TABLE IF NOT EXISTS product_blasts (
        id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        -- The Melbourne calendar day the attempt was for.
        blast_date       DATE NOT NULL,
        -- posted | skipped | blocked | failed | retracted
        status           TEXT NOT NULL,
        headline         TEXT,
        bullets          JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- Changelog versions this attempt looked at (strings).
        versions         JSONB NOT NULL DEFAULT '[]'::jsonb,
        -- Why it was skipped, blocked or failed, in words a person can read.
        reason           TEXT,
        model            TEXT,
        raw_output       TEXT,
        orgs_notified    INTEGER NOT NULL DEFAULT 0,
        created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        retracted_at     TIMESTAMPTZ
    )
    """,
    # One posted blast per day. The index, not a read-then-write check, is what
    # stops a scheduled run and a manual Run now both posting.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_product_blasts_posted_day
        ON product_blasts (blast_date) WHERE status = 'posted'
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_product_blasts_created
        ON product_blasts (created_at DESC)
    """,
    *BACKFILL_STATEMENTS,
]

# Downgrade drops only what this migration added.
DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS product_blasts",
    "DROP TABLE IF EXISTS product_blast_control",
]
