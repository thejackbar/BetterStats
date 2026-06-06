"""KlubPro → BetterStats migration tooling: sponsor contact columns + audit/rollback.

Adds the three sponsor columns the KlubPro sponsor import targets
(``contact_name``, ``email``, ``klubpro_sponsor_id``) plus a partial-unique index
so a sponsor can't be brought across twice for the same org, and the two
BetterStats-side bookkeeping tables that make every player/sponsor import
auditable and reversible:

  * ``klubpro_migration_batches`` — one executed import (the unit of rollback).
  * ``klubpro_migration_backups`` — per-row before/after image (a player UPDATE
    keeps the old values; a sponsor INSERT records the new id to delete on undo).

All additive / idempotent — single-club orgs and existing sponsors are untouched.

Revision ID: 072
Revises: 071
Create Date: 2026-06-06

"""
from alembic import op


revision = '072'
down_revision = '071'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── org_sponsors: contact details + source id (idempotent — the app lifespan
    # also adds these defensively so the API boots before alembic runs). ────────
    op.execute("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS contact_name TEXT")
    op.execute("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS email TEXT")
    op.execute("ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS klubpro_sponsor_id TEXT")
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_org_sponsor_klubpro "
        "ON org_sponsors(organisation_id, klubpro_sponsor_id) "
        "WHERE klubpro_sponsor_id IS NOT NULL"
    )

    # ── audit + rollback bookkeeping ───────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS klubpro_migration_batches (
            id UUID PRIMARY KEY,
            kind TEXT NOT NULL,
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            club_mapping_id UUID,
            klubpro_club_id TEXT,
            status TEXT NOT NULL DEFAULT 'imported',
            counts JSONB,
            operator_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            operator_name TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            rolled_back_at TIMESTAMPTZ
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kp_batches_org "
        "ON klubpro_migration_batches(organisation_id, created_at DESC)"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS klubpro_migration_backups (
            id UUID PRIMARY KEY,
            batch_id UUID NOT NULL REFERENCES klubpro_migration_batches(id) ON DELETE CASCADE,
            target_table TEXT NOT NULL,
            target_id UUID NOT NULL,
            action TEXT NOT NULL,
            before_data JSONB,
            after_data JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_kp_backups_batch "
        "ON klubpro_migration_backups(batch_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS klubpro_migration_backups")
    op.execute("DROP TABLE IF EXISTS klubpro_migration_batches")
    op.execute("DROP INDEX IF EXISTS uq_org_sponsor_klubpro")
    op.execute("ALTER TABLE org_sponsors DROP COLUMN IF EXISTS klubpro_sponsor_id")
    op.execute("ALTER TABLE org_sponsors DROP COLUMN IF EXISTS email")
    op.execute("ALTER TABLE org_sponsors DROP COLUMN IF EXISTS contact_name")
