"""club_room_public_link — a shareable, PIN-gated public link for Club Room
Mode, so a club can leave a TV running on the /room/{token} page without ever
needing an admin session on that browser. Same link+PIN+cookie posture as
BetterSelect's self-service availability and vote-collection links
(availability_link_token / vote_settings.link_token), just scoped to one
settings row per club instead of a column on organisations.

Revision ID: 210
Revises: 209
Create Date: 2026-08-02
"""
from alembic import op

revision = '210'
down_revision = '209'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS link_token TEXT"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_club_room_settings_link_token "
        "ON club_room_settings(link_token) WHERE link_token IS NOT NULL"
    )
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS public_link_enabled "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS require_pin "
        "BOOLEAN NOT NULL DEFAULT true"
    )
    op.execute(
        "ALTER TABLE club_room_settings ADD COLUMN IF NOT EXISTS pin_hash TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS pin_hash")
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS require_pin")
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS public_link_enabled")
    op.execute("ALTER TABLE club_room_settings DROP COLUMN IF EXISTS link_token")
