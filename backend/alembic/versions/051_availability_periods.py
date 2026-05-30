"""BetterSelect: availability periods (date-range un/availability).

Lets an admin mark a player available / unavailable / maybe across a span of
dates in one action — e.g. "injured 1 Jun–15 Jul", or open-ended "out until
further notice" (NULL end_date) — instead of clicking every fixture date.

A covering period supplies a date's status wherever no explicit per-date
``player_availability`` row exists; an explicit row always wins. This keeps the
existing per-date model authoritative and layers periods underneath as a
convenience default.

Revision ID: 051
Revises: 050
Create Date: 2026-05-30
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '051'
down_revision = '050'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "player_availability_periods",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True),
                  sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),   # NULL = open-ended
        sa.Column("status", sa.Text(), nullable=False),     # AVAILABLE | UNAVAILABLE | MAYBE
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("recorded_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recorded_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_avail_periods_org", "player_availability_periods", ["organisation_id"])
    op.create_index("ix_avail_periods_player", "player_availability_periods", ["player_id"])
    op.create_index(
        "ix_avail_periods_lookup", "player_availability_periods",
        ["organisation_id", "start_date", "end_date"],
    )


def downgrade() -> None:
    op.drop_index("ix_avail_periods_lookup", table_name="player_availability_periods")
    op.drop_index("ix_avail_periods_player", table_name="player_availability_periods")
    op.drop_index("ix_avail_periods_org", table_name="player_availability_periods")
    op.drop_table("player_availability_periods")
