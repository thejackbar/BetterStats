"""BetterSelect: per-player cricket attributes for selection filters.

Adds the attributes the selection filter panel needs (batting hand, bowling
action, bowling type, opening batter). All nullable / opt-in — synced players
start blank and admins fill them in.

Revision ID: 050
Revises: 049
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa


revision = '050'
down_revision = '049'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("players", sa.Column("batting_hand", sa.Text(), nullable=True))      # 'LEFT' | 'RIGHT'
    op.add_column("players", sa.Column("bowling_action", sa.Text(), nullable=True))    # 'RIGHT_ARM' | 'LEFT_ARM'
    op.add_column("players", sa.Column("bowling_type", sa.Text(), nullable=True))      # FAST|FAST_MEDIUM|MEDIUM|MEDIUM_FAST|FINGER_SPIN|WRIST_SPIN
    op.add_column("players", sa.Column("is_opening_batsman", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "is_opening_batsman")
    op.drop_column("players", "bowling_type")
    op.drop_column("players", "bowling_action")
    op.drop_column("players", "batting_hand")
