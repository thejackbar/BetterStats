"""Add is_club_innings flag to partnerships

Partnership records were attributed to a club whenever either batter belonged
to that club's player set. An opposition innings that happened to include a
former club player therefore surfaced as a club partnership record (with the
non-club partner showing as a blank name).

This adds a per-row flag marking whether the partnership occurred in the
club's own innings, set at sync time from the scorecard. Existing rows are
left NULL ("unknown"); the records/yearbook queries treat NULL as "fall back
to requiring both batters to be club players", which already excludes the
mixed opposition partnerships. A hard refresh repopulates the flag properly.

No backfill is run here on purpose: batting_innings only stores club players'
rows (opposition batters are never inserted), so an innings-level roster vote
over that table would misclassify every innings as the club's.

Revision ID: 014
Revises: 013
Create Date: 2026-05-18
"""
from alembic import op
import sqlalchemy as sa

revision = '014'
down_revision = '013'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('partnerships', sa.Column('is_club_innings', sa.Boolean(), nullable=True))


def downgrade():
    op.drop_column('partnerships', 'is_club_innings')
