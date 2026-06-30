"""Per-module subscription status + Club General Settings + primary admin

Moves entitlement from one org-wide ``subscription_status`` to a per-module model.
``org_module_subscriptions`` is the source of truth for which modules a club holds
and each module's own status / renewal / trial window; ``module_overrides`` stays
as a denormalised currently-held cache for the fast synchronous gate (see
app/auth/modules.py). The org-level ``subscription_status`` becomes a whole-account
master switch above these rows.

Also adds:
  - ``organisations.general_settings`` (JSONB) — extensible per-club Club General
    Settings blob; first field is ``default_trial_days`` (read as 14 when absent).
  - ``club_memberships.is_primary_admin`` — the club's primary/owner admin
    (one per club), backfilled to the earliest club_admin; only the primary may
    request a paid subscription.

Backfill is non-breaking: every module already in ``module_overrides`` gets a row
inheriting the club's current org-wide status + renewal, so no club changes
entitlement on deploy.

Mirrored idempotently in main.py lifespan.

Revision ID: 118
Revises: 117
Create Date: 2026-06-30
"""
from alembic import op


revision = '118'
down_revision = '117'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── Club General Settings blob ───────────────────────────────────────────
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "general_settings JSONB NOT NULL DEFAULT '{}'"
    )

    # ── Primary / owner admin ────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE club_memberships ADD COLUMN IF NOT EXISTS "
        "is_primary_admin BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_membership_primary "
        "ON club_memberships(club_id) WHERE is_primary_admin"
    )
    # Backfill: the earliest club_admin per club becomes primary (skip clubs that
    # already have one). DISTINCT ON picks the oldest membership per club.
    op.execute("""
        UPDATE club_memberships m
        SET is_primary_admin = true
        FROM (
            SELECT DISTINCT ON (club_id) id
            FROM club_memberships
            WHERE role = 'club_admin'
            ORDER BY club_id, created_at ASC, id ASC
        ) first
        WHERE m.id = first.id
          AND NOT EXISTS (
            SELECT 1 FROM club_memberships x
            WHERE x.club_id = m.club_id AND x.is_primary_admin
          )
    """)

    # ── Per-module subscriptions ─────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS org_module_subscriptions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            module_key TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            trial_started_at TIMESTAMPTZ,
            trial_ends_at TIMESTAMPTZ,
            renewal_date DATE,
            started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_org_module UNIQUE (organisation_id, module_key)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_org_module_subscriptions_org "
        "ON org_module_subscriptions(organisation_id)"
    )

    # Backfill one row per held module, inheriting the club's current org-wide
    # status + renewal. For a club whose master switch is paused/cancelled we still
    # record the module as held with status 'active' (the master switch hides it),
    # so unpausing restores access exactly as today. ON CONFLICT keeps it idempotent.
    op.execute("""
        INSERT INTO org_module_subscriptions
            (organisation_id, module_key, status, renewal_date, started_at, created_at, updated_at)
        SELECT
            o.id,
            m.module_key,
            CASE WHEN o.subscription_status IN ('active','trial','past_due')
                 THEN o.subscription_status ELSE 'active' END,
            o.renewal_date,
            NOW(), NOW(), NOW()
        FROM organisations o
        CROSS JOIN LATERAL jsonb_array_elements_text(COALESCE(o.module_overrides, '[]'::jsonb)) AS m(module_key)
        WHERE m.module_key IN ('select','socials','fees','iq','comms','merch','fantasy')
        ON CONFLICT (organisation_id, module_key) DO NOTHING
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS org_module_subscriptions")
    op.execute("DROP INDEX IF EXISTS uq_membership_primary")
    op.execute("ALTER TABLE club_memberships DROP COLUMN IF EXISTS is_primary_admin")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS general_settings")
