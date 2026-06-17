"""BetterFantasyCricket — draft mode (drafts, picks, wishlists, waivers, trades, h2h)

The draft engine's tables. A draft league (fantasy_leagues.kind = 'draft') runs an
async snake or auction draft into uniquely-owned squads, then plays out on a
total-points or head-to-head ladder with waivers and trades. Full design:
docs/betterfantasycricket.md.

Mirrored idempotently in main.py's lifespan so the API boots before alembic runs.

Revision ID: 088
Revises: 087
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '088'
down_revision = '087'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'fantasy_drafts',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('type', sa.Text(), nullable=False, server_default='snake'),     # snake | auction
        sa.Column('status', sa.Text(), nullable=False, server_default='scheduled'),  # scheduled | in_progress | complete
        sa.Column('pick_seconds', sa.Integer(), nullable=False, server_default='14400'),
        sa.Column('current_pick', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('draft_order', JSONB(), nullable=False, server_default='[]'),
        sa.Column('rounds', sa.Integer(), nullable=False, server_default='12'),
        sa.Column('started_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('league_id', name='uq_fantasy_draft_league'),
    )

    op.create_table(
        'fantasy_draft_picks',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('draft_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_drafts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('pick_index', sa.Integer(), nullable=False),
        sa.Column('round_no', sa.Integer(), nullable=False),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('deadline', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('picked_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('auto_picked', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('bid_amount', sa.Numeric(8, 1), nullable=True),
        sa.UniqueConstraint('draft_id', 'pick_index', name='uq_fantasy_draft_pick'),
    )
    op.create_index('ix_fantasy_draft_picks_draft', 'fantasy_draft_picks', ['draft_id', 'pick_index'])

    op.create_table(
        'fantasy_draft_wishlists',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('draft_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_drafts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_ids', JSONB(), nullable=False, server_default='[]'),
        sa.UniqueConstraint('draft_id', 'manager_id', name='uq_fantasy_draft_wishlist'),
    )

    op.create_table(
        'fantasy_waiver_claims',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('add_player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('drop_player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('processed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('ix_fantasy_waiver_claims_league', 'fantasy_waiver_claims', ['league_id', 'status'])

    op.create_table(
        'fantasy_trades',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('proposer_squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('receiver_squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('offer', JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.Text(), nullable=False, server_default='proposed'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('ix_fantasy_trades_league', 'fantasy_trades', ['league_id', 'status'])

    op.create_table(
        'fantasy_h2h_fixtures',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_rounds.id', ondelete='SET NULL'), nullable=True),
        sa.Column('round_no', sa.Integer(), nullable=False),
        sa.Column('home_squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('away_squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='SET NULL'), nullable=True),
        sa.Column('home_points', sa.Numeric(8, 2), nullable=True),
        sa.Column('away_points', sa.Numeric(8, 2), nullable=True),
        sa.Column('result', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_fantasy_h2h_fixtures_league', 'fantasy_h2h_fixtures', ['league_id', 'round_no'])


def downgrade() -> None:
    op.drop_table('fantasy_h2h_fixtures')
    op.drop_table('fantasy_trades')
    op.drop_table('fantasy_waiver_claims')
    op.drop_table('fantasy_draft_wishlists')
    op.drop_table('fantasy_draft_picks')
    op.drop_table('fantasy_drafts')
