"""social_media_and_brand_kit — BetterSocials club media library
(social_media_asset: per-club uploaded image pool, bytes stored in-table like
club/sponsor logos) + a per-club brand kit JSON blob
(organisations.social_brand_kit).

Revision ID: 191
Revises: 190
Create Date: 2026-07-29
"""
from alembic import op

revision = '191'
down_revision = '190'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS social_media_asset (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            filename TEXT,
            mime TEXT,
            image_data BYTEA,
            width INTEGER,
            height INTEGER,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_social_media_asset_organisation_id "
        "ON social_media_asset(organisation_id)"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS social_brand_kit JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS social_brand_kit")
    op.execute("DROP TABLE IF EXISTS social_media_asset")
