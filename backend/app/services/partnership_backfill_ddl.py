"""The DDL behind the partnership backfill's undo log (migration 359), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``partnership_backfill_log``
    One row per game the backfill (``app.scripts.backfill_partnerships --apply``) wrote
    to: the ids of the ``partnerships`` and ``fall_of_wickets`` rows it inserted, written in
    the SAME transaction as the rows, so a run that is killed half way is still undoable.
    ``--undo`` deletes exactly those ids and stamps ``undone_at``; rows are never deleted
    by code. ``game_id`` has no foreign key so the record outlives a Full Rebuild.
    ``run_id`` groups the games of one invocation.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS partnership_backfill_log (
        id SERIAL PRIMARY KEY,
        run_id UUID NOT NULL,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        partnership_ids INTEGER[] NOT NULL DEFAULT '{}',
        fow_ids INTEGER[] NOT NULL DEFAULT '{}',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        undone_at TIMESTAMPTZ
    )""",
    "CREATE INDEX IF NOT EXISTS ix_partnership_backfill_log_org ON partnership_backfill_log (organisation_id, created_at)",
    "CREATE INDEX IF NOT EXISTS ix_partnership_backfill_log_run ON partnership_backfill_log (run_id)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS partnership_backfill_log",
]
