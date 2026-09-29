"""Super-admin messages to club admins on their dashboard (migration 312).

`admin_broadcasts` is the message and its rules: who it is for (every club, a
set of clubs, or a set of named users, optionally narrowed to Club Admins or
the Primary Club Admin), when it starts and stops, and what makes it go away
(a super admin clearing it, each recipient dismissing it, each recipient
seeing it once, or anybody at the club seeing it once).

`admin_broadcast_receipts` is one row per (message, user) the first time that
user's dashboard shows it, plus when they dismissed it. It is what the
view-once and dismissible rules read, and what the super admin's "seen by"
figures count. Super admins and sales staff never write one: they see a club's
messages as a preview, and a preview must not use up somebody's view-once.

ONE copy of the DDL, per the vote_medal_ddl rule — alembic's 312 and main.py's
lifespan mirror both run STATEMENTS. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS admin_broadcasts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        message TEXT NOT NULL,
        tone TEXT NOT NULL DEFAULT 'info',
        link_url TEXT,
        link_label TEXT,
        audience TEXT NOT NULL DEFAULT 'all',
        audience_roles TEXT NOT NULL DEFAULT 'all_admins',
        org_ids UUID[] NOT NULL DEFAULT '{}',
        user_ids UUID[] NOT NULL DEFAULT '{}',
        persistence TEXT NOT NULL DEFAULT 'until_cleared',
        starts_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        expires_at TIMESTAMPTZ,
        cleared_at TIMESTAMPTZ,
        cleared_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_admin_broadcasts_live
        ON admin_broadcasts (starts_at) WHERE cleared_at IS NULL
    """,
    """
    CREATE TABLE IF NOT EXISTS admin_broadcast_receipts (
        broadcast_id UUID NOT NULL REFERENCES admin_broadcasts(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        organisation_id UUID REFERENCES organisations(id) ON DELETE CASCADE,
        first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        dismissed_at TIMESTAMPTZ,
        PRIMARY KEY (broadcast_id, user_id)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_admin_broadcast_receipts_org
        ON admin_broadcast_receipts (broadcast_id, organisation_id)
    """,
]

DOWNGRADE = [
    "DROP TABLE IF EXISTS admin_broadcast_receipts",
    "DROP TABLE IF EXISTS admin_broadcasts",
]
