"""Membership Management + Family/Household.

Adds a cross-season ``membership_types`` catalogue (Senior Player, Junior
Player, Parent, Life Member, Coach, Committee Member, …) — a club-adopted
catalogue in the same "seed a starter set, or don't" spirit as the award and
CRM tracker templates, not a fixed list. ``fee_members`` gains
``membership_type_id`` plus ``is_life_member``/``is_honorary``/
``honorary_expires_at`` (cross-season, since these don't reset each season);
``fee_member_seasons`` gains ``status`` (the per-season lifecycle:
prospect → invited → … → active → suspended → expired → archived), defaulted
to 'active' so every existing row reads exactly as it did before this
migration.

Extends the existing ``family_members`` table (previously player-only) to
also hold non-playing family members — parents/guardians — via a new
nullable ``fee_member_id`` (parents are FeeMember rows with no player_id,
same as any other manual/non-playing member), alongside the existing
``player_id`` (made nullable; untouched for every existing row).
``is_guardian`` marks a responsible adult; ``receives_family_comms`` lets a
separated parent opt out of the "whole family" communications grouping
while staying part of the family structurally.

Revision ID: 175
Revises: 174
Create Date: 2026-07-23
"""
from alembic import op


revision = '175'
down_revision = '174'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS membership_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            default_annual_fee NUMERIC(10,2),
            is_playing BOOLEAN NOT NULL DEFAULT false,
            requires_voting_rights BOOLEAN NOT NULL DEFAULT false,
            requires_insurance BOOLEAN NOT NULL DEFAULT false,
            requires_wwcc BOOLEAN NOT NULL DEFAULT false,
            requires_playhq_registration BOOLEAN NOT NULL DEFAULT false,
            comms_group TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_membership_types_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_membership_types_org ON membership_types(organisation_id, is_active)")

    op.execute(
        "ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS membership_type_id UUID "
        "REFERENCES membership_types(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS is_life_member BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS is_honorary BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS honorary_expires_at DATE")
    op.execute("CREATE INDEX IF NOT EXISTS ix_fee_members_type ON fee_members(membership_type_id)")

    op.execute("ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS status TEXT NOT NULL DEFAULT 'active'")

    op.execute("ALTER TABLE family_members ALTER COLUMN player_id DROP NOT NULL")
    op.execute(
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS fee_member_id UUID "
        "REFERENCES fee_members(id) ON DELETE CASCADE"
    )
    op.execute("ALTER TABLE family_members ADD COLUMN IF NOT EXISTS is_guardian BOOLEAN NOT NULL DEFAULT false")
    op.execute(
        "ALTER TABLE family_members ADD COLUMN IF NOT EXISTS receives_family_comms BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_family_member_fee_member
        ON family_members(family_id, fee_member_id) WHERE fee_member_id IS NOT NULL
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_family_member_fee_member")
    op.execute("ALTER TABLE family_members DROP COLUMN IF EXISTS receives_family_comms")
    op.execute("ALTER TABLE family_members DROP COLUMN IF EXISTS is_guardian")
    op.execute("ALTER TABLE family_members DROP COLUMN IF EXISTS fee_member_id")
    op.execute("ALTER TABLE family_members ALTER COLUMN player_id SET NOT NULL")
    op.execute("ALTER TABLE fee_member_seasons DROP COLUMN IF EXISTS status")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS honorary_expires_at")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS is_honorary")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS is_life_member")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS membership_type_id")
    op.execute("DROP TABLE IF EXISTS membership_types")
