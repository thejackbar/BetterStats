"""BetterSelect Phase 2: fixture availability.

Admin-recorded availability of players for upcoming fixtures (club-wide
model: all active players x upcoming fixtures, regardless of team).
recorded_by/at track which admin set it; there is no player-facing input.

Revision ID: 045
Revises: 044
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '045'
down_revision = '044'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fixture_availability",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("fixture_id", UUID(as_uuid=True),
                  sa.ForeignKey("fixtures.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True),
                  sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="NO_RESPONSE"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("fixture_id", "player_id", name="uq_fixture_availability_fixture_player"),
    )
    op.create_index("ix_fixture_availability_fixture", "fixture_availability", ["fixture_id"])
    op.create_index("ix_fixture_availability_player", "fixture_availability", ["player_id"])


def downgrade() -> None:
    op.drop_index("ix_fixture_availability_player", table_name="fixture_availability")
    op.drop_index("ix_fixture_availability_fixture", table_name="fixture_availability")
    op.drop_table("fixture_availability")
