"""club_room_mode — auto-rotating TV slideshow (sponsors, fixtures/lineups,
recent social posts, custom images) a club leaves running in the club room.

club_room_settings: one row per club (enabled + default rotation length).
club_room_slides: the saved playlist — an ordered list of slide-type entries,
each expanding into one or more rendered slides on read (e.g. a "sponsors"
entry becomes one slide per sponsor).
club_room_media: shared image pool for admin-uploaded custom images and
social-post exports saved from the BetterSocials composer, bytes stored
in-table like every other image feature in this app.

Revision ID: 206
Revises: 205
Create Date: 2026-08-02
"""
from alembic import op

revision = '206'
down_revision = '205'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_room_settings (
            organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
            enabled BOOLEAN NOT NULL DEFAULT false,
            rotation_seconds INTEGER NOT NULL DEFAULT 15,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_room_slides (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            slide_type TEXT NOT NULL,
            title TEXT,
            config JSONB NOT NULL DEFAULT '{}'::jsonb,
            duration_seconds INTEGER,
            position INTEGER NOT NULL DEFAULT 0,
            enabled BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_room_slides_org "
        "ON club_room_slides(organisation_id, position)"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_room_media (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            source TEXT NOT NULL DEFAULT 'upload',
            caption TEXT,
            image_data BYTEA NOT NULL,
            image_mime TEXT NOT NULL,
            created_by UUID,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_room_media_org "
        "ON club_room_media(organisation_id, source, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS club_room_media")
    op.execute("DROP TABLE IF EXISTS club_room_slides")
    op.execute("DROP TABLE IF EXISTS club_room_settings")
