"""BetterSelect: repair player_availability (in-place 045 rewrite fallout).

Migration 045 was rewritten in place: it originally created a
`fixture_availability` table and was later changed to create
`player_availability`. Alembic keys on the revision id, not file contents, so
any database that ran the ORIGINAL 045 has `045` recorded as applied and skips
the rewritten version — leaving `player_availability` missing (and an orphan
`fixture_availability`). The availability matrix then 500s with
'relation "player_availability" does not exist'.

This migration is fully idempotent and converges ANY db state to correct:
- creates `player_availability` IF NOT EXISTS (matching the 045 model),
- drops the orphan `fixture_availability` IF EXISTS.

On a clean DB where the rewritten 045 already created player_availability,
every statement here is a no-op.

Revision ID: 046
Revises: 045
Create Date: 2026-05-29
"""
from alembic import op


revision = '046'
down_revision = '045'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS player_availability (
            id SERIAL PRIMARY KEY,
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
            avail_date DATE NOT NULL,
            status TEXT NOT NULL DEFAULT 'NO_RESPONSE',
            note TEXT,
            recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
            recorded_at TIMESTAMPTZ DEFAULT now(),
            created_at TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_player_availability_player_date UNIQUE (player_id, avail_date)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_player_availability_org_date "
        "ON player_availability (organisation_id, avail_date)"
    )
    # Remove the orphan table the original 045 may have created.
    op.execute("DROP TABLE IF EXISTS fixture_availability")


def downgrade() -> None:
    # No-op: 045 owns the table's lifecycle, and this is a forward repair.
    pass
