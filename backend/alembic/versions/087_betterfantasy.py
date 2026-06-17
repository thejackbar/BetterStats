"""BetterFantasyCricket — internal club fantasy league (phase 1 data model)

The scoring, pricing, rounds, leagues and squad spine for the fantasy module.
Players are the club's own playing list; matches are the club's own fixtures.
Fantasy points are computed from the per-innings stats we already hold. Full
design: docs/betterfantasycricket.md.

All tables are org-scoped and prefixed `fantasy_`. The draft mechanics tables
(drafts, picks, waivers, trades, head-to-head fixtures) land in a later phase.

Mirrored idempotently in main.py's lifespan so the API boots before alembic runs.

Revision ID: 087
Revises: 086
Create Date: 2026-06-17

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '087'
down_revision = '086'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The public fantasy link token lives on the org (like BetterSelect's
    # availability link) so a printed QR stays stable across seasons; it
    # resolves to the club's currently-open fantasy season.
    op.add_column('organisations', sa.Column('fantasy_link_token', sa.Text(), nullable=True))

    # 1. fantasy_seasons — one per (org, season_year); the umbrella for both engines.
    op.create_table(
        'fantasy_seasons',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('season_year', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('status', sa.Text(), nullable=False, server_default='setup'),
        sa.Column('included_grade_ids', JSONB(), nullable=True),  # null = all grades
        sa.Column('scoring', JSONB(), nullable=False, server_default='{}'),
        sa.Column('rules', JSONB(), nullable=False, server_default='{}'),
        sa.Column('registration_open', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('organisation_id', 'season_year', name='uq_fantasy_season_org_year'),
    )

    # 2. fantasy_managers — a human entrant (member or supporter), per org.
    op.create_table(
        'fantasy_managers',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('credential_hash', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index('ix_fantasy_managers_org', 'fantasy_managers', ['organisation_id'])
    op.create_index(
        'uq_fantasy_manager_org_email', 'fantasy_managers', ['organisation_id', 'email'],
        unique=True, postgresql_where=sa.text('email IS NOT NULL'),
    )

    # 3. fantasy_leagues — a competition grouping. The global salary-cap league is
    #    auto-created with the season; mini-leagues and draft leagues are added.
    op.create_table(
        'fantasy_leagues',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fantasy_season_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False, server_default='global_salary_cap'),  # global_salary_cap | mini_salary_cap | draft
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('join_code', sa.Text(), nullable=True),
        sa.Column('draft_type', sa.Text(), nullable=True),     # snake | auction
        sa.Column('scoring_type', sa.Text(), nullable=True),   # total | h2h
        sa.Column('settings', JSONB(), nullable=False, server_default='{}'),
        sa.Column('status', sa.Text(), nullable=False, server_default='open'),
        sa.Column('created_by_manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_fantasy_leagues_season', 'fantasy_leagues', ['fantasy_season_id', 'kind'])
    op.create_index(
        'uq_fantasy_league_join_code', 'fantasy_leagues', ['fantasy_season_id', 'join_code'],
        unique=True, postgresql_where=sa.text('join_code IS NOT NULL'),
    )

    # 4. fantasy_squads — a manager's team in a league (global salary cap, or a draft league).
    op.create_table(
        'fantasy_squads',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fantasy_season_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('team_name', sa.Text(), nullable=False),
        sa.Column('budget_remaining', sa.Numeric(8, 1), nullable=True),    # salary cap only
        sa.Column('free_transfers', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('chips_used', JSONB(), nullable=False, server_default='{}'),
        sa.Column('total_points', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('joined_round', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('league_id', 'manager_id', name='uq_fantasy_squad_league_manager'),
    )
    op.create_index('ix_fantasy_squads_season', 'fantasy_squads', ['fantasy_season_id'])

    # 5. fantasy_squad_players — the current picks of a squad.
    op.create_table(
        'fantasy_squad_players',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='batter'),
        sa.Column('is_captain', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_vice_captain', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('purchase_price', sa.Numeric(8, 1), nullable=True),
        sa.Column('added_round', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('squad_id', 'player_id', name='uq_fantasy_squad_player'),
    )
    op.create_index('ix_fantasy_squad_players_squad', 'fantasy_squad_players', ['squad_id'])

    # 6. fantasy_league_members — manager ↔ league ↔ the squad ranked there.
    op.create_table(
        'fantasy_league_members',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=False),
        sa.Column('manager_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_managers.id', ondelete='CASCADE'), nullable=False),
        sa.Column('squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='SET NULL'), nullable=True),
        sa.Column('joined_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('league_id', 'manager_id', name='uq_fantasy_league_member'),
    )
    op.create_index('ix_fantasy_league_members_league', 'fantasy_league_members', ['league_id'])

    # 7. fantasy_pool_players — the pickable pool, one row per player per season.
    op.create_table(
        'fantasy_pool_players',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fantasy_season_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('role', sa.Text(), nullable=False, server_default='batter'),
        sa.Column('role_source', sa.Text(), nullable=False, server_default='auto'),  # admin | profile | auto
        sa.Column('base_price', sa.Numeric(8, 1), nullable=False, server_default='0'),
        sa.Column('current_price', sa.Numeric(8, 1), nullable=False, server_default='0'),
        sa.Column('total_points', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('last_round_points', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('owned_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('price_change', sa.Numeric(6, 1), nullable=False, server_default='0'),
        sa.Column('is_available', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('fantasy_season_id', 'player_id', name='uq_fantasy_pool_player'),
    )
    op.create_index('ix_fantasy_pool_players_season', 'fantasy_pool_players', ['fantasy_season_id'])

    # 8. fantasy_rounds — generated from the real game calendar (grouped by weekend).
    op.create_table(
        'fantasy_rounds',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fantasy_season_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.Text(), nullable=True),
        sa.Column('lock_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('start_date', sa.Date(), nullable=True),
        sa.Column('end_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='upcoming'),  # upcoming | locked | scored
        sa.Column('scored_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('fantasy_season_id', 'round_number', name='uq_fantasy_round_number'),
    )
    op.create_index('ix_fantasy_rounds_season', 'fantasy_rounds', ['fantasy_season_id', 'round_number'])

    # 9. fantasy_player_round_scores — computed points per player per round.
    op.create_table(
        'fantasy_player_round_scores',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('fantasy_season_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_seasons.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_rounds.id', ondelete='CASCADE'), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='CASCADE'), nullable=False),
        sa.Column('base_points', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('total_points', sa.Numeric(8, 2), nullable=False, server_default='0'),
        sa.Column('breakdown', JSONB(), nullable=False, server_default='{}'),
        sa.Column('games_counted', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('computed_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('round_id', 'player_id', name='uq_fantasy_player_round_score'),
    )
    op.create_index('ix_fantasy_player_round_scores_round', 'fantasy_player_round_scores', ['fantasy_season_id', 'round_id'])

    # 10. fantasy_squad_round_scores — per squad per round, with the lineup snapshot.
    op.create_table(
        'fantasy_squad_round_scores',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('round_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_rounds.id', ondelete='CASCADE'), nullable=False),
        sa.Column('points', sa.Numeric(8, 2), nullable=False, server_default='0'),       # best-11 incl captain, minus hit
        sa.Column('raw_points', sa.Numeric(8, 2), nullable=False, server_default='0'),   # before the transfer hit
        sa.Column('transfer_hit', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('transfers_made', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('chip_used', sa.Text(), nullable=True),
        sa.Column('captain_player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('vice_captain_player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('dropped_player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('lineup', JSONB(), nullable=False, server_default='[]'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('squad_id', 'round_id', name='uq_fantasy_squad_round_score'),
    )
    op.create_index('ix_fantasy_squad_round_scores_round', 'fantasy_squad_round_scores', ['round_id'])

    # 11. fantasy_transactions — transfer / waiver / draft-pick / trade / chip audit log.
    op.create_table(
        'fantasy_transactions',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='CASCADE'), nullable=False),
        sa.Column('league_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_leagues.id', ondelete='CASCADE'), nullable=True),
        sa.Column('round_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_rounds.id', ondelete='SET NULL'), nullable=True),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('counterparty_squad_id', UUID(as_uuid=True), sa.ForeignKey('fantasy_squads.id', ondelete='SET NULL'), nullable=True),
        sa.Column('price', sa.Numeric(8, 1), nullable=True),
        sa.Column('detail', JSONB(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_fantasy_transactions_squad', 'fantasy_transactions', ['squad_id', 'created_at'])


def downgrade() -> None:
    op.drop_table('fantasy_transactions')
    op.drop_table('fantasy_squad_round_scores')
    op.drop_table('fantasy_player_round_scores')
    op.drop_table('fantasy_rounds')
    op.drop_table('fantasy_pool_players')
    op.drop_table('fantasy_league_members')
    op.drop_table('fantasy_squad_players')
    op.drop_table('fantasy_squads')
    op.drop_table('fantasy_leagues')
    op.drop_table('fantasy_managers')
    op.drop_table('fantasy_seasons')
    op.drop_column('organisations', 'fantasy_link_token')
