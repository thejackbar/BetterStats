"""BetterComms Phase 2 — saved dynamic segments

A segment is a SAVED QUERY, not a stored list: a named set of rules
(``definition`` JSONB) evaluated against the club's contacts at send time, joined
to the player + current-season stats we already hold. This is the BetterComms
edge over a newsletter tool — "played 10+ matches", "in the women's squad",
"a committee tag" — because the cricket data is right there. See
services/comms_segments.py and docs/bettercomms-architecture.md.

Mirrored idempotently in main.py lifespan.

Revision ID: 111
Revises: 110
Create Date: 2026-06-26
"""
from alembic import op


revision = '111'
down_revision = '110'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS comms_segments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            definition JSONB NOT NULL DEFAULT '{}',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_comms_segment_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_comms_segments_org ON comms_segments(organisation_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS comms_segments")
