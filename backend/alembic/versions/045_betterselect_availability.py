"""BetterSelect Phase 2: player availability (per playing date).

Availability is keyed on (player, date) — NOT per fixture. One answer for a
playing date covers every fixture that day. A two-day game contributes both
its dates (played_on = week 1, end_on = week 2), so a player can be available
week 1 and unavailable week 2; that same week-1 answer also covers any one-day
fixture on the week-1 date.

Admin-recorded (club-wide model): recorded_by/at track which admin set it.

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
        "player_availability",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True),
                  sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("avail_date", sa.Date(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="NO_RESPONSE"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("recorded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("player_id", "avail_date", name="uq_player_availability_player_date"),
    )
    op.create_index(
        "ix_player_availability_org_date", "player_availability", ["organisation_id", "avail_date"]
    )


def downgrade() -> None:
    op.drop_index("ix_player_availability_org_date", table_name="player_availability")
    op.drop_table("player_availability")
