"""The DDL behind fall of wickets a club typed from its own scorebook (migration 357), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``fow_overrides``
    One row per wicket a club entered for a synced match. Cricket Australia's own
    scorecard is sometimes short of fall of wickets (six wickets, four rows), and the
    club's paper scorebook has the rest. The typed rows replace the synced ones for that
    innings, and the partnerships are worked out again from them.

    ``game_id`` has NO foreign key on purpose. A Full Rebuild deletes every synced game
    and pulls it back under the same id, which would cascade a foreign key and take the
    club's typing with it. The rows are re-applied to the game as sync stores it again.
    ``participant_id`` is the batter's raw Cricket Australia id (text), so a player merge
    or a late registration is resolved when the rows are applied, not frozen here.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS fow_overrides (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        innings_number INTEGER NOT NULL,
        wicket_number INTEGER NOT NULL,
        score_at_fall INTEGER,
        participant_id TEXT,
        batter_name TEXT,
        entered_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_fow_overrides_wicket UNIQUE (organisation_id, game_id, innings_number, wicket_number)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_fow_overrides_game ON fow_overrides (game_id)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS fow_overrides",
]
