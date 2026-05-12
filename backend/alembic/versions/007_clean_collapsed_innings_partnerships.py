"""Delete partnerships from games where both innings were collapsed into innings_number=1

CA's Grassroots API returns `inningsNumber: 1` for both innings of a match
(their data bug), while `inningsOrder` (1, 2) is the field that actually
distinguishes them. Our sync was keying off `inningsNumber`, so for every
multi-innings game, both teams' batting/FOW/partnership rows were stored
under `innings_number=1` — masking the FOW-vs-dismissals check added in
migration 006 (e.g. 5 mismatched dismissals coincidentally matching 5 total
FOW rows pooled from both innings).

The smoking gun is `fall_of_wickets` having duplicate `wicket_number` values
within a single (game_id, innings_number) — impossible in a real innings.
This migration deletes the bogus partnerships AND the collapsed FOW rows for
those games so they can be rebuilt cleanly on the next hard refresh.

`batting_innings` rows are NOT touched — their innings_number is mostly
cosmetic (per-player per-game stats don't change), and wiping them would
force a slow full re-sync rather than just a hard refresh of partnerships.

Idempotent.

Revision ID: 007
Revises: 006
Create Date: 2026-05-12
"""
from alembic import op

revision = '007'
down_revision = '006'
branch_labels = None
depends_on = None


_POISONED_GAMES_SQL = """
    SELECT DISTINCT game_id
    FROM fall_of_wickets
    GROUP BY game_id, innings_number, wicket_number
    HAVING COUNT(*) > 1
"""


def upgrade() -> None:
    op.execute(
        f"""
        DELETE FROM partnerships
        WHERE game_id IN ({_POISONED_GAMES_SQL})
        """
    )
    op.execute(
        f"""
        DELETE FROM fall_of_wickets
        WHERE game_id IN ({_POISONED_GAMES_SQL})
        """
    )


def downgrade() -> None:
    pass
