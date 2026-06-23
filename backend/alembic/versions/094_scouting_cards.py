"""BetterIQ scouting cards — manual batting/bowling intel (the data CA can't give us)

Cricket Australia's community feed is scorecard-level: runs, wickets, dismissal
type — but NO shot direction, no delivery length/line, no bowler-type-faced.
A scout's read of HOW a batter gets out (vulnerable to pace short outside off,
favours the pull) or HOW a bowler operates (stock off-spin, has a doosra, attacks
the stumps) is therefore manual intel, same posture as the existing scout-entered
scoring-zones wagon wheel.

This adds a structured "scouting card" — kept as two JSONB blobs (batting / bowling)
so the shape can evolve without a migration per field — for BOTH:

* opponent players — extra columns on the existing ``opponent_player_tags``
  (keyed by CA participant GUID, org-scoped, merged onto the live dossier on read);
* our own players — a new ``player_scouting_cards`` table (keyed by ``players.id``,
  org-scoped), surfaced in BetterIQ Player trends.

Revision ID: 094
Revises: 093
Create Date: 2026-06-23
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID


revision = '094'
down_revision = '093'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Opponent players — extend the existing scouting-tag row.
    op.add_column('opponent_player_tags', sa.Column('batting_intel', JSONB(), nullable=True))
    op.add_column('opponent_player_tags', sa.Column('bowling_intel', JSONB(), nullable=True))

    # Our own players — a parallel store keyed by the real players row.
    op.create_table(
        'player_scouting_cards',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), nullable=False),
        sa.Column('batting_intel', JSONB(), nullable=True),
        sa.Column('bowling_intel', JSONB(), nullable=True),
        sa.Column('updated_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['player_id'], ['players.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisation_id', 'player_id', name='uq_player_scouting_org_player'),
    )


def downgrade() -> None:
    op.drop_table('player_scouting_cards')
    op.drop_column('opponent_player_tags', 'bowling_intel')
    op.drop_column('opponent_player_tags', 'batting_intel')
