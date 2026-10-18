"""Locked-down club users (migration 344).

A Club Admin account can be locked to ONE module (BetterSelect only, say), or given
a choice of menu items each at View or Manage. The row here is the source of truth
for that choice: `club_memberships` still holds
the account's one home membership, set to role `club_member`, and its
`capabilities` list is a cache derived from this row (services/access.py).

No row means no restriction: a `club_admin` with no row has every capability,
exactly as before. A row is keyed on (user, club) rather than on the user so the
later per-club grants for linked clubs and the per-menu-item version need no
new table shape; today only the account's home club is ever written.

ONE copy of the DDL, per the vote_medal_ddl rule: alembic's 344, main.py's
lifespan mirror and the football schema mirror
(services/afl/cricket_schema_mirror.SHARED_DDL_MODULES) all run STATEMENTS, the
last because the shared `/auth/me` and `require_cap` read the table for a
football club's users too. Every statement is idempotent.
"""

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS user_access (
        user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        club_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        mode TEXT NOT NULL,
        module_key TEXT,
        grants JSONB NOT NULL DEFAULT '{}',
        updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (user_id, club_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_user_access_club ON user_access (club_id)",
    # Per-item access: {"select.availability": "view", "admin.fees": "manage", ...}.
    # Empty for a person locked to a whole module (mode 'module'). Written before
    # this column shipped, a table created without it still gets it here.
    "ALTER TABLE user_access ADD COLUMN IF NOT EXISTS grants JSONB NOT NULL DEFAULT '{}'",
    # The capabilities in club_memberships.capabilities held at view level only.
    "ALTER TABLE club_memberships ADD COLUMN IF NOT EXISTS view_only_caps JSONB NOT NULL DEFAULT '[]'",
]

# Drops only what this migration added: the table and the one membership column.
# The membership rows it set to `club_member` keep that role and their cached
# capabilities, so a downgrade leaves each locked user able to open the same
# screens (a person held at view level would then be able to edit them too).
DOWNGRADE = [
    "DROP INDEX IF EXISTS ix_user_access_club",
    "DROP TABLE IF EXISTS user_access",
    "ALTER TABLE club_memberships DROP COLUMN IF EXISTS view_only_caps",
]
