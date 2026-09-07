"""A player's shirt number, and the club's record of what size kit they take.

Three fields, and they deliberately do NOT live in the same place, because they
are not the same kind of fact.

``players.shirt_number``
    A PLAYING attribute, so it sits with the rest of them on the player. It is
    what goes on a team sheet, a lineup post and a scorecard, and a club running
    nothing but BetterStats has every one of those surfaces — so gating it
    behind a paid module would leave a Core club unable to put a number on its
    own team sheet. TEXT, not an integer, for the same reason
    ``afl_player_game_lines.jumper_number`` is: a club that issues "07" or "00"
    means it, and an integer column quietly makes them 7 and 0.

``fee_members.shirt_size`` / ``.pants_size``
    KIT MANAGEMENT, which is a BetterAdmin concern, so they sit on the person
    spine the Directory already edits. On the spine rather than on ``players``
    because a coach, a scorer and a canteen volunteer all get a club polo and
    none of them is a player — ``players`` has nowhere to put their size. The
    Directory is the one screen that writes them; a Stats-only club is told the
    fields exist and where they live rather than being shown a dead control.

All three are free text and NULL by default, so no club reads differently the
day this lands. Nothing anywhere normalises a size to a vocabulary: a club buys
from whichever supplier it buys from, and "Youth 12", "2XL" and "34" are all
real answers somebody has to be able to type.

Revision ID: 288
Revises: 287
"""
from alembic import op

revision = "288"
down_revision = "287"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE players ADD COLUMN IF NOT EXISTS shirt_number TEXT")
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS shirt_size TEXT")
    op.execute("ALTER TABLE fee_members ADD COLUMN IF NOT EXISTS pants_size TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS pants_size")
    op.execute("ALTER TABLE fee_members DROP COLUMN IF EXISTS shirt_size")
    op.execute("ALTER TABLE players DROP COLUMN IF EXISTS shirt_number")
