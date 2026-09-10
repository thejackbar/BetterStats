"""The ONE copy of the scorecard-import staging DDL.

Alembic (migration 302) and `main.py`'s lifespan mirror both run this list, in
this order, per the `vote_medal_ddl` rule — two copies is how the two drift.
Every statement is idempotent, because the lifespan re-runs the whole list on
every boot.

WHY A TABLE RATHER THAN THE MEDIA VOLUME. These rows are transient by
construction — they live for one sitting of the import wizard and are deleted
the moment it commits — so they must never be backed up, and
`/mnt/media/bettercricket/internal/videos` is deliberately OUTSIDE the regular
backup for the opposite reason (a video is permanent and merely too big to
dump). A table is also what makes expiry and club scoping one DELETE rather
than a directory walk, and this is text.
"""

STATEMENTS: list[str] = [
    # `rows` is the PARSED sheet, keyed by our own column names — the exact
    # shape `_resolve_games` reads — so the sheet is parsed ONCE, at preview,
    # rather than re-parsed on every override change.
    #
    # Scoped to the club AND the user: a token is an opaque handle to one
    # person's half-finished import, and the club is what stops a token from
    # one club reaching another's staged history.
    """
    CREATE TABLE IF NOT EXISTS manual_game_import_staging (
        token TEXT PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        filename TEXT,
        row_count INTEGER NOT NULL DEFAULT 0,
        unknown_columns JSONB NOT NULL DEFAULT '[]'::jsonb,
        rows JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ NOT NULL
    )
    """,
    # Read on every sweep, so it is worth the index: the sweep runs on each
    # preview and would otherwise scan every club's staged rows to find the
    # handful that have lapsed.
    """
    CREATE INDEX IF NOT EXISTS idx_manual_game_import_staging_expires
        ON manual_game_import_staging (expires_at)
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_manual_game_import_staging_org
        ON manual_game_import_staging (organisation_id, user_id)
    """,
]
