"""player squad assignment (selection pool)

Adds `players.squad_team_id` — the team a player is assigned to as their
selection pool (distinct from historical TeamMember squad membership). Drives
the "suggested first" ordering in BetterSelect selection and the squad tag on
the redesigned Players screen.

(`is_overseas` / `overseas_country` already exist from 036_overseas_player.)

Revision ID: 053_player_squad_team
Revises: 052_club_default_team_size
Create Date: 2026-05-30

"""
from alembic import op
import sqlalchemy as sa


revision = '053_player_squad_team'
down_revision = '052_club_default_team_size'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'players',
        sa.Column(
            'squad_team_id',
            sa.UUID(as_uuid=True),
            sa.ForeignKey('teams.id', ondelete='SET NULL'),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column('players', 'squad_team_id')
