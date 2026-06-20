"""manual_game_scorecard_payload — hold the full extracted scorecard on a manual game.

The "Upload Historical Scorecard" tool reads a photographed scorecard with Claude
vision and stores the result as a manual game. Our own players are normalised into
manual_batting_innings / manual_bowling_spells / manual_fielding_stats as usual, but
two extra bits of the card have nowhere to live yet:

  - opp_org_id    — the opposition club's Grassroots org GUID, picked from the same
                    CA club search onboarding uses. Mirrors games.opp_org_id, so the
                    manual game links up with head-to-head / BetterIQ opponent
                    matching (which read COALESCE(opp_org_id, opp_club_name)). The
                    club's display name already lives in manual_games.opposition.
  - extracted_payload — the whole both-team scorecard the model returned (both
                    innings, opposition batting/bowling, fall of wickets, toss,
                    extras). It is the source of truth for rendering the OPPOSITION
                    half of the match view (the opposition aren't stored as player
                    rows), and the data we'd promote into real records if that club
                    ever joins.

Both additive + idempotent; nothing reads them until the tool ships, so the columns
are inert on existing rows.

Revision ID: 091
Revises: 090
Create Date: 2026-06-20

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision = '091'
down_revision = '090'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('manual_games', sa.Column('opp_org_id', sa.Text(), nullable=True))
    op.add_column('manual_games', sa.Column('extracted_payload', JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column('manual_games', 'extracted_payload')
    op.drop_column('manual_games', 'opp_org_id')
