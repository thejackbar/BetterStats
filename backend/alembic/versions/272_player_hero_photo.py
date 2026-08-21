"""A player's action shot, alongside their headshot.

``players.hero_photo_data`` / ``.hero_photo_mime`` / ``.hero_photo_url``

A headshot and an action shot are two different photographs doing two
different jobs, and a club needs both. The headshot is the square mugshot
that reads at 44px on a roster row, in a squad grid, beside a name. The
action shot is the one that fills a match-day post — a player mid-cover-
drive, shot at distance, cropped tall.

They could not share one column. Cropping a headshot into the full-height
hero slot of a team-sheet post magnifies a face to the point of parody
(which is what asked for this), and shrinking an action shot into a 44px
circle leaves a smudge of whites and grass. So the club stores both and
each surface takes the one it wants.

Bytes live in-table exactly as ``photo_data`` already does — the upload
volume on this box is not guaranteed to persist, which is the same reason
club logos, sponsor logos and committee photos are all stored this way.
Served from ``GET /api/images/players/{id}/hero-photo``.

Nothing syncs this. Cricket Australia's feeds carry no photography at all,
so both columns are the club uploading what it holds.

Revision ID: 272
Revises: 271
"""
from alembic import op

revision = "272"
down_revision = "271"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS hero_photo_data BYTEA")
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS hero_photo_mime TEXT")
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS hero_photo_url TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS hero_photo_url")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS hero_photo_mime")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS hero_photo_data")
