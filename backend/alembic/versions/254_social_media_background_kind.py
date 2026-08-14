"""social_media_background_kind — tags a social_media_asset as a reusable
club-uploaded post BACKGROUND (kind='background') vs an ordinary photo
(kind NULL), so BetterSocials can offer a small per-club background library
separate from the general Photos upload pool, off the same table.

Revision ID: 254
Revises: 253
Create Date: 2026-08-14
"""
from alembic import op

revision = '254'
down_revision = '253'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE social_media_asset ADD COLUMN IF NOT EXISTS kind TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE social_media_asset DROP COLUMN IF EXISTS kind")
