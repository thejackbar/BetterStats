"""Show the club crest beside the club name in public page headers.

A club that has uploaded a logo only ever saw it in the menu bar; the page
header itself was the club name as plain text. Opt-in rather than on by
default, so no established club's public site changes appearance because of an
upgrade.

Revision ID: 226
Revises: 225
"""
from alembic import op

revision = "226"
down_revision = "225"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "public_header_logo BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS public_header_logo")
