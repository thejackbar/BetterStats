"""BetterIQ: opposition_dossiers cache table

Better pivot · Phase 4 / BetterIQ — opposition analysis. Caches the assembled
opponent scouting dossier (current-season squad + form fetched live from the
grade's Grassroots scorecards, plus player-level head-to-head vs us). Built on
demand; `status` drives the build/poll UX, `built_at` drives a freshness TTL +
manual refresh. See app/services/iq_opponent.py.

Revision ID: 059
Revises: 058
Create Date: 2026-06-01

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '059'
down_revision = '058'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'opposition_dossiers',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('opp_key', sa.Text(), nullable=False),
        sa.Column('opp_name', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='building'),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('built_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisation_id', 'opp_key', name='uq_dossier_org_opp'),
    )


def downgrade() -> None:
    op.drop_table('opposition_dossiers')
