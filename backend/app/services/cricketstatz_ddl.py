"""Schema for the CricketStatz import — the ONE copy alembic and the lifespan
mirror both run, per the vote_medal_ddl rule.

Every statement is idempotent, because the lifespan re-runs the whole list on
each boot.

Three ideas:

* ``cricketstatz_imports`` is the batch. Everything an import writes carries
  its id, so the whole pull can be undone as a unit.
* ``cricketstatz_records`` is the club's record book as CricketStatz computed
  it (highest totals, biggest winning margins, top aggregates…), captured
  generically — a title, headers and rows — because there are ~180 report
  shapes and modelling each one is neither possible nor useful.
* The identity columns. ``players.cricketstatz_player_id`` holds the stable
  per-player id every report links, which is a far better key than the printed
  name; ``manual_games.cricketstatz_match_id`` makes re-importing a club
  update its matches rather than double its history.
"""

STATEMENTS: tuple[str, ...] = (
    # ── the batch ────────────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cricketstatz_imports (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL
            REFERENCES organisations(id) ON DELETE CASCADE,
        club_id TEXT NOT NULL,
        club_name TEXT,
        source_url TEXT,
        status TEXT NOT NULL DEFAULT 'running',
        phase TEXT,
        progress JSONB,
        stats JSONB,
        error TEXT,
        started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        finished_at TIMESTAMPTZ,
        undone_at TIMESTAMPTZ,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_cricketstatz_imports_org
        ON cricketstatz_imports (organisation_id, started_at DESC)
    """,
    # ── the record book ──────────────────────────────────────────────────────
    """
    CREATE TABLE IF NOT EXISTS cricketstatz_records (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL
            REFERENCES organisations(id) ON DELETE CASCADE,
        import_id UUID REFERENCES cricketstatz_imports(id) ON DELETE CASCADE,
        mode INTEGER NOT NULL,
        section TEXT,
        title TEXT NOT NULL,
        scope TEXT,
        headers JSONB,
        rows JSONB,
        row_count INTEGER NOT NULL DEFAULT 0,
        captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # One live copy of each report per club: a re-import replaces a board
    # rather than stacking a second copy beside it.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_cricketstatz_records_org_mode
        ON cricketstatz_records (organisation_id, mode)
    """,
    # ── identity ─────────────────────────────────────────────────────────────
    """
    ALTER TABLE players
        ADD COLUMN IF NOT EXISTS cricketstatz_player_id TEXT
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_players_org_cricketstatz
        ON players (organisation_id, cricketstatz_player_id)
        WHERE cricketstatz_player_id IS NOT NULL
    """,
    """
    ALTER TABLE manual_games
        ADD COLUMN IF NOT EXISTS cricketstatz_match_id TEXT
    """,
    """
    ALTER TABLE manual_games
        ADD COLUMN IF NOT EXISTS cricketstatz_import_id UUID
            REFERENCES cricketstatz_imports(id) ON DELETE SET NULL
    """,
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_manual_games_org_cricketstatz
        ON manual_games (organisation_id, cricketstatz_match_id)
        WHERE cricketstatz_match_id IS NOT NULL
    """,
    # The club's own site, remembered so a re-import needs no re-typing.
    """
    ALTER TABLE organisations
        ADD COLUMN IF NOT EXISTS cricketstatz_club_id TEXT
    """,
)

DOWNGRADE: tuple[str, ...] = (
    "DROP INDEX IF EXISTS uq_manual_games_org_cricketstatz",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS cricketstatz_import_id",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS cricketstatz_match_id",
    "DROP INDEX IF EXISTS uq_players_org_cricketstatz",
    "ALTER TABLE players DROP COLUMN IF EXISTS cricketstatz_player_id",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS cricketstatz_club_id",
    "DROP TABLE IF EXISTS cricketstatz_records",
    "DROP TABLE IF EXISTS cricketstatz_imports",
)
