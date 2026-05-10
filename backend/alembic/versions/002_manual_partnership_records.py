"""Add manual_partnership_records table

Revision ID: 002
Revises: 001
Create Date: 2026-05-09
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '002'
down_revision = '001_saas_foundations'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "manual_partnership_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batter1_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("batter1_name", sa.Text(), nullable=False),
        sa.Column("batter2_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("batter2_name", sa.Text(), nullable=False),
        sa.Column("grade_name", sa.Text(), nullable=False),
        sa.Column("season_year", sa.Integer(), nullable=False),
        sa.Column("wicket_number", sa.Integer(), nullable=False),
        sa.Column("runs", sa.Integer(), nullable=False),
        sa.Column("is_not_out", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("manual_partnership_records")
