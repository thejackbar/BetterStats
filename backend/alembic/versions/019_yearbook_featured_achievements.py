"""Add yearbook_featured_achievements for pinning pulled awards to overview

Revision ID: 019
Revises: 018
Create Date: 2026-05-19
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '019'
down_revision = '018'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yearbook_featured_achievements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("yearbook_id", UUID(as_uuid=True), sa.ForeignKey("yearbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", UUID(as_uuid=True), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("yearbook_id", "achievement_id", name="uq_yb_featured_achievement"),
    )
    op.create_index("ix_yb_featured_yearbook", "yearbook_featured_achievements", ["yearbook_id"])


def downgrade() -> None:
    op.drop_table("yearbook_featured_achievements")
