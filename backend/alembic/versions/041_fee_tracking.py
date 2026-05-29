"""Fee tracking (Phase 1).

A self-contained membership / match-fee ledger that sits alongside the stats
data. Adds:

- grades.fee_format: per-grade override for how a grade is treated for fees
  (two_day / one_day / t20 / women / exclude). NULL = derive from
  games.match_format. Needed because women's (PSWL) grades arrive as plain
  One Day / T20 and can't otherwise be told apart.
- fee_schedule: per-season membership tiers (the spreadsheet's PARMS rate card).
- fee_members: every fee-paying person; linked to a stats player where one
  exists, manual otherwise (life members, sponsors, non-playing ICL).
- fee_member_seasons: per-member-per-season financial state (which tier).
- fee_match_days: per-game match-day contributions, auto-derived from
  appearances each sync, overridable by admins.
- fee_payments: bank-reconciled payments (defined now; wired in Phase 2).

Revision ID: 041
Revises: 040
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '041'
down_revision = '040'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ─── grades.fee_format ────────────────────────────────────────────────────
    op.add_column("grades", sa.Column("fee_format", sa.Text(), nullable=True))

    # ─── fee_schedule ─────────────────────────────────────────────────────────
    op.create_table(
        "fee_schedule",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("payment_type", sa.Text(), server_default="standard", nullable=False),
        sa.Column("membership_amount", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("match_day_rate", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("display_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("season_id", "name", name="uq_fee_schedule_season_name"),
    )
    op.create_index("ix_fee_schedule_season", "fee_schedule", ["season_id"])

    # ─── fee_members ──────────────────────────────────────────────────────────
    op.create_table(
        "fee_members",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("full_name", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("mobile", sa.Text(), nullable=True),
        sa.Column("current_tier", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        # NULLs are distinct in Postgres, so multiple manual members (player_id
        # NULL) coexist fine; this only blocks two members sharing one player.
        sa.UniqueConstraint("organisation_id", "player_id", name="uq_fee_member_org_player"),
    )
    op.create_index("ix_fee_members_org", "fee_members", ["organisation_id"])

    # ─── fee_member_seasons ───────────────────────────────────────────────────
    op.create_table(
        "fee_member_seasons",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("member_id", UUID(as_uuid=True), sa.ForeignKey("fee_members.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("fee_schedule_id", UUID(as_uuid=True), sa.ForeignKey("fee_schedule.id", ondelete="SET NULL"), nullable=True),
        sa.Column("is_new_registration", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("membership_payment_method", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("member_id", "season_id", name="uq_fee_member_season"),
    )
    op.create_index("ix_fee_member_seasons_season", "fee_member_seasons", ["season_id"])
    op.create_index("ix_fee_member_seasons_org_season", "fee_member_seasons", ["organisation_id", "season_id"])

    # ─── fee_match_days ───────────────────────────────────────────────────────
    op.create_table(
        "fee_match_days",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("member_season_id", UUID(as_uuid=True), sa.ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("game_id", UUID(as_uuid=True), sa.ForeignKey("games.id", ondelete="CASCADE"), nullable=True),
        sa.Column("played_at", sa.Date(), nullable=True),
        sa.Column("fee_format", sa.Text(), nullable=True),
        sa.Column("days_played", sa.Numeric(3, 1), server_default="1", nullable=False),
        sa.Column("auto_derived", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("override_reason", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("member_season_id", "game_id", name="uq_fee_match_day_member_game"),
    )
    op.create_index("ix_fee_match_days_member_season", "fee_match_days", ["member_season_id"])

    # ─── fee_payments (Phase 2 surface; created now to keep that change additive)
    op.create_table(
        "fee_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("member_season_id", UUID(as_uuid=True), sa.ForeignKey("fee_member_seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("organisation_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("amount", sa.Numeric(10, 2), server_default="0", nullable=False),
        sa.Column("paid_at", sa.Date(), nullable=True),
        sa.Column("kind", sa.Text(), server_default="membership", nullable=False),
        sa.Column("method", sa.Text(), nullable=True),
        sa.Column("bank_ref", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_fee_payments_member_season", "fee_payments", ["member_season_id"])


def downgrade() -> None:
    op.drop_table("fee_payments")
    op.drop_table("fee_match_days")
    op.drop_table("fee_member_seasons")
    op.drop_table("fee_members")
    op.drop_table("fee_schedule")
    op.drop_column("grades", "fee_format")
