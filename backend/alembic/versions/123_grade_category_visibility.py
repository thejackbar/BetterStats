"""Grade category label + public visibility

Adds two columns to ``grades`` so clubs can label grades (Senior / Junior /
Women's / Masters / Mixed) and choose which ones to share on their public site:

- ``category`` TEXT — the public-facing category key. NULL = uncategorised
  (readers fall back to a name-based suggestion). Attaches to a grade name
  club-wide, like ``display_name_override``.
- ``is_public`` BOOLEAN NOT NULL DEFAULT true — whether the grade shows on the
  club's public grade surfaces. Defaults true so nothing changes for existing
  clubs until they opt a grade out.

Both are additive and backward-compatible. Mirrored idempotently in main.py
lifespan so the API boots even if alembic hasn't run yet.

Revision ID: 123
Revises: 122
Create Date: 2026-07-01
"""
from alembic import op


revision = '123'
down_revision = '122'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE grades ADD COLUMN IF NOT EXISTS category TEXT")
    op.execute(
        "ALTER TABLE grades ADD COLUMN IF NOT EXISTS "
        "is_public BOOLEAN NOT NULL DEFAULT true"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS is_public")
    op.execute("ALTER TABLE grades DROP COLUMN IF EXISTS category")
