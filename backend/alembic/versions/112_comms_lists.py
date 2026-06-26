"""BetterComms Phase 2 — saved static lists

A static list is a curated, fixed set of contacts (committee, sponsors, a team
roster), the counterpart to a dynamic segment. ``comms_lists`` is the named list;
``comms_list_members`` is its membership (FK-cascaded to both the list and the
contact, so a deleted contact drops out cleanly). A list is a valid campaign
audience (``{type: "saved_list", list_id}``). See
docs/bettercomms-architecture.md.

Mirrored idempotently in main.py lifespan.

Revision ID: 112
Revises: 111
Create Date: 2026-06-26
"""
from alembic import op


revision = '112'
down_revision = '111'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS comms_lists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comms_list_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_comms_lists_org ON comms_lists(organisation_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS comms_list_members (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            list_id UUID NOT NULL REFERENCES comms_lists(id) ON DELETE CASCADE,
            contact_id UUID NOT NULL REFERENCES comms_contacts(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comms_list_member UNIQUE (list_id, contact_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_comms_list_members_list ON comms_list_members(list_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comms_list_members")
    op.execute("DROP TABLE IF EXISTS comms_lists")
