"""Add source column to player_season_stats.

Distinguishes API-sourced rows (CA's aggregate per-season totals) from
backfill-synthesised rows produced by _backfill_missing_season_stats
when CA's API omits a (player, season) pair but per-game tables have it.

Used by cleanup_opposition_stats to avoid wiping legitimate aggregate-
only rows for pre-PlayHQ-migration players whose data exists only as
career-style summaries on the CA side (no per-game scorecards, no
appearances).

Existing rows default to 'api'. The opposition-stats phantom cleanup
that pre-dates this column may have already removed some real rows
on the few orgs that ran the button; those need to be restored by a
subsequent Sync Now (the aggregate sync delete-then-replaces per
season from CA's API, so anything CA still returns is re-inserted).

Revision ID: 040
Revises: 039
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '040'
down_revision = '039'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'player_season_stats',
        sa.Column('source', sa.Text(), nullable=False, server_default='api'),
    )


def downgrade() -> None:
    op.drop_column('player_season_stats', 'source')
