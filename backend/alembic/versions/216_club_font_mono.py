"""Third club typography role: numbers/stats (mono), alongside display and body.

font_config already supports arbitrary role keys (JSONB), so only the
uploaded-bytes columns need adding here — mirrors font_display_data/mime and
font_body_data/mime from migration 215.

Revision ID: 216
Revises: 215
Create Date: 2026-08-04
"""
from alembic import op

revision = "216"
down_revision = "215"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_mono_data BYTEA"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_mono_mime TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_mono_mime")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_mono_data")
