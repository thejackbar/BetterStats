"""BetterScout — Scout Org tenant tables

A Scout Org is a brand-new top-level tenant type (a recruiting agency like
CricExchange, or a premier club scouting its own feeder-club juniors), NOT
an Organisation row — no relationship to any club, no PlayHQ id, and its
users never touch the existing users/club_memberships tables or the
bs_session cookie those use. See services/scout_auth.py for the completely
separate login/session mechanism these tables back, and routers/scout/auth.py
(mounted at /scout/auth) for the endpoints.

Lives in the same database as everything else — deliberately not a separate
silo (unlike AFL): BetterScout doesn't need its own server infrastructure to
be its own tenant type with its own login. Logical isolation (these two
tables have zero foreign keys to/from organisations, players, users, etc.)
is what actually matters here, not a separate database.

Revision ID: 236
Revises: 235
"""
from alembic import op

revision = "236"
down_revision = "235"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_orgs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            slug TEXT UNIQUE,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            primary_color TEXT DEFAULT '#16c784',
            accent_color TEXT DEFAULT '#243352',
            theme_mode TEXT DEFAULT 'dark',
            logo_url TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            username TEXT NOT NULL UNIQUE,
            email TEXT,
            password_hash TEXT,
            display_name TEXT,
            role TEXT NOT NULL DEFAULT 'owner',
            last_login_at TIMESTAMPTZ,
            failed_login_count INTEGER NOT NULL DEFAULT 0,
            locked_until TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_users_org ON scout_users(scout_org_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_users")
    op.execute("DROP TABLE IF EXISTS scout_orgs")
