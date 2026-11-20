"""An association workspace's crest library: every club's crest, kept once.

One row per (workspace, Cricket Australia club id). The crest is fetched from
Cricket Australia the first time a pull names the club, its plain background is
taken off (services/association_crests.py), and every later post reuses it. A
person can upload a replacement (`uploaded_png`), turn the automatic clean-up
off (`use_cleaned`) or set the colour by hand (`colour_by_hand`); a refresh by
code never touches any of those.

One copy: alembic migration 393 and main.py's lifespan both run STATEMENTS. Every
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
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS association_crests",
]
