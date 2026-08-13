"""BetterScout — internal-club link on scouted_players

When a scouted player's club is already an onboarded BetterCricket club,
services/scout_internal_link.py builds their roster/career from our own
per-game tables instead of Cricket Australia's public aggregate API —
richer, exact, and free. internal_org_id / internal_player_id record which
real organisation/player a scouted player resolved to, so later refreshes
and Milestones' exact-match dating don't have to re-resolve every time.

Deliberately plain UUID columns with NO foreign key — models/scout.py's
whole isolation guarantee is zero FKs in or out of any scout_* table (see
its module docstring). A club deleting a player later must not be able to
break anything on the BetterScout side; a stale internal_player_id here
just means the next refresh falls back to re-resolving (or, if the club no
longer resolves at all, to the public-API path).

Revision ID: 241
Revises: 240
"""
from alembic import op

revision = "241"
down_revision = "240"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS internal_org_id UUID"
    )
    op.execute(
        "ALTER TABLE scouted_players ADD COLUMN IF NOT EXISTS internal_player_id UUID"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE scouted_players DROP COLUMN IF EXISTS internal_player_id")
    op.execute("ALTER TABLE scouted_players DROP COLUMN IF EXISTS internal_org_id")
