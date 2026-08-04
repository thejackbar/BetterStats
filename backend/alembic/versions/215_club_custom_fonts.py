"""Per-club custom typography for the public-facing club site.

Two independent roles — display (headings) and body (paragraph text) — each
either left unset (app default), pointed at a curated built-in preset (a
Google Fonts family already loaded site-wide, see frontend/src/lib/theme.js
FONT_PRESETS), or an uploaded font file (e.g. a club's own licensed
Clash Display .woff2, to match their own website). font_config carries the
per-role selection; the uploaded bytes for each role live in their own
columns, mirroring the existing logo_data/logo_mime pattern.

Revision ID: 215
Revises: 214
Create Date: 2026-08-04
"""
from alembic import op

revision = "215"
down_revision = "214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_config JSONB"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_display_data BYTEA"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_display_mime TEXT"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_body_data BYTEA"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "font_body_mime TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_body_mime")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_body_data")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_display_mime")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_display_data")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS font_config")
