"""BetterScout — org settings, invites, share-link expiry stamp

Ten settings columns on scout_orgs (org profile, plan/refresh cadence, the
Overview "stale" threshold, Discover/Profile default window, sharing
defaults, milestone digest). scout_invites is the pending-teammate queue
behind the Settings "People" card's read-only invite row. share_token_created_at
on scout_watchlist_cards is what lets share_expiry_days actually be enforced
(get_shared_card) — the token itself carries no timestamp otherwise, and
card.updated_at changes on every edit, not just on share/regenerate.

Revision ID: 242
Revises: 241
"""
from alembic import op

revision = "242"
down_revision = "241"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in [
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS org_type TEXT",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS home_region TEXT",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS refresh_cadence TEXT NOT NULL DEFAULT 'weekly'",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS stale_after_weeks INTEGER NOT NULL DEFAULT 6",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS default_window TEXT NOT NULL DEFAULT '2'",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_include_notes BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_include_tags BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS share_expiry_days INTEGER DEFAULT 90",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS digest_enabled BOOLEAN NOT NULL DEFAULT TRUE",
        "ALTER TABLE scout_orgs ADD COLUMN IF NOT EXISTS alert_scope TEXT NOT NULL DEFAULT 'all_tracked'",
        "ALTER TABLE scout_watchlist_cards ADD COLUMN IF NOT EXISTS share_token_created_at TIMESTAMPTZ",
    ]:
        op.execute(stmt)

    op.execute("""
        CREATE TABLE IF NOT EXISTS scout_invites (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scout_org_id UUID NOT NULL REFERENCES scout_orgs(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            token TEXT NOT NULL UNIQUE,
            invited_by UUID REFERENCES scout_users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            accepted_at TIMESTAMPTZ,
            expires_at TIMESTAMPTZ NOT NULL
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_scout_invites_org ON scout_invites(scout_org_id)"
    )
    # Only one live (unaccepted, unexpired doesn't matter here — just
    # unaccepted) invite per email per org, so re-inviting the same address
    # updates in place rather than piling up duplicate rows.
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_scout_invites_org_email_pending "
        "ON scout_invites(scout_org_id, email) WHERE accepted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS scout_invites")
    for stmt in [
        "ALTER TABLE scout_watchlist_cards DROP COLUMN IF EXISTS share_token_created_at",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS alert_scope",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS digest_enabled",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS share_expiry_days",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS share_include_tags",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS share_include_notes",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS default_window",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS stale_after_weeks",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS refresh_cadence",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS home_region",
        "ALTER TABLE scout_orgs DROP COLUMN IF EXISTS org_type",
    ]:
        op.execute(stmt)
