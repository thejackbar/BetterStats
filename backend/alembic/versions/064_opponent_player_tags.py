"""BetterIQ: opponent_player_tags — manual scouting attributes for opponents

Opposition players aren't synced into our tables (only the live dossier JSON
holds their stats). This table lets a club annotate them — handedness, bowling
type, role, a "danger man" flag and free-text notes — keyed by the opponent's
Cricket Australia participant GUID (the dossier's player_id). Org-scoped: each
club keeps its own scouting book. Decoupled from the 7-day dossier cache, so the
tags are merged on read and survive every rebuild.

Revision ID: 064
Revises: 063
Create Date: 2026-06-04

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '064'
down_revision = '063'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'opponent_player_tags',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('participant_id', sa.Text(), nullable=False),   # CA participant GUID (dossier player_id)
        sa.Column('player_name', sa.Text(), nullable=True),       # denormalised display name
        sa.Column('batting_hand', sa.Text(), nullable=True),      # LEFT | RIGHT
        sa.Column('bowling_action', sa.Text(), nullable=True),    # RIGHT_ARM | LEFT_ARM
        sa.Column('bowling_type', sa.Text(), nullable=True),      # FAST|FAST_MEDIUM|MEDIUM|MEDIUM_FAST|FINGER_SPIN|WRIST_SPIN
        sa.Column('player_role', sa.Text(), nullable=True),       # BAT | BOWL | ALL | WK (free-ish)
        sa.Column('is_wicket_keeper', sa.Boolean(), nullable=True),
        sa.Column('is_danger', sa.Boolean(), nullable=True),      # manual "danger man" flag
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('updated_by', UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisation_id', 'participant_id', name='uq_opponent_tag_org_participant'),
    )


def downgrade() -> None:
    op.drop_table('opponent_player_tags')
