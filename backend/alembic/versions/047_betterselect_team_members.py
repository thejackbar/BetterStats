"""BetterSelect: manual squad membership (player <-> team).

The club-wide model intentionally has no player->team link. This adds an
OPTIONAL, admin-managed one: a team's "squad" — the pool you actually select
from for that team. History still drives *suggestions* (who's played for this
team recently), but assignment here is the source of truth.

Many-to-many: a player can be in several teams' squads (a 1st XI batter who
drops to the 2nds, an all-format player, etc.). Keyed (team_id, player_id).

Revision ID: 047
Revises: 046
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '047'
down_revision = '046'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "team_members",
        sa.Column("team_id", UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True),
                  sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("added_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_team_members_org", "team_members", ["organisation_id"])
    op.create_index("ix_team_members_player", "team_members", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_team_members_player", table_name="team_members")
    op.drop_index("ix_team_members_org", table_name="team_members")
    op.drop_table("team_members")
