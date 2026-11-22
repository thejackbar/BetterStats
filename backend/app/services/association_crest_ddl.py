"""An association workspace's crest library: every club's crest, kept once.

One row per (workspace, Cricket Australia club id). The crest is fetched from
Cricket Australia the first time a pull names the club, its plain background is
taken off (services/association_crests.py), and every later post reuses it. A
person can upload a replacement (`uploaded_png`), turn the automatic clean-up
off (`use_cleaned`) or set the colour by hand (`colour_by_hand`); a refresh by
code never touches any of those.

One copy: alembic migrations 393 and 394 and main.py's lifespan run STATEMENTS. Every
statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS association_crests (
        workspace_id UUID NOT NULL,
        ca_org_id TEXT NOT NULL,
        name TEXT,
        src_url TEXT,
        original_png BYTEA,
        cleaned_png BYTEA,
        uploaded_png BYTEA,
        use_cleaned BOOLEAN NOT NULL DEFAULT TRUE,
        colour TEXT,
        colour2 TEXT,
        colour_by_hand BOOLEAN NOT NULL DEFAULT FALSE,
        version TEXT,
        uploaded_by UUID,
        uploaded_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        PRIMARY KEY (workspace_id, ca_org_id)
    )
    """,
    # Migration 394: how the cut-out is made (auto, plain, or on a white edge)
    # and which clean-up made it, so a better one re-cleans kept crests from
    # their original without fetching them again.
    "ALTER TABLE association_crests ADD COLUMN IF NOT EXISTS cut_style TEXT NOT NULL DEFAULT 'auto'",
    "ALTER TABLE association_crests ADD COLUMN IF NOT EXISTS clean_version INTEGER NOT NULL DEFAULT 1",
]

# What migration 394 adds on its own (393 ran the list before these existed).
STATEMENTS_394 = STATEMENTS[1:]
DOWNGRADE_394 = [
    "ALTER TABLE association_crests DROP COLUMN IF EXISTS clean_version",
    "ALTER TABLE association_crests DROP COLUMN IF EXISTS cut_style",
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS association_crests",
]
