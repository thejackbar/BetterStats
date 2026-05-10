"""Add phq_id_suggestions table

Revision ID: 004
Revises: 003
Create Date: 2026-05-10
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '004'
down_revision = '003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "phq_id_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="CASCADE"), nullable=True),
        sa.Column("phq_player_id", sa.Text(), nullable=False),
        sa.Column("phq_first_name", sa.Text(), nullable=True),
        sa.Column("phq_last_name", sa.Text(), nullable=True),
        sa.Column("confidence", sa.Text(), nullable=False),  # 'auto' | 'high' | 'low'
        sa.Column("game_count", sa.Integer(), server_default="1"),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),  # pending | approved | dismissed
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("resolved_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.UniqueConstraint("org_id", "phq_player_id", name="uq_phq_suggestions_org_phq"),
    )
    op.create_index("ix_phq_id_suggestions_status", "phq_id_suggestions", ["status"])
    op.create_index("ix_phq_id_suggestions_org", "phq_id_suggestions", ["org_id"])


def downgrade() -> None:
    op.drop_table("phq_id_suggestions")
