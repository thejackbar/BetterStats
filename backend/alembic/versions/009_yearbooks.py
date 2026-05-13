"""Add yearbook tables for v4 Yearbook feature

Revision ID: 009
Revises: 008
Create Date: 2026-05-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = '009'
down_revision = '008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "yearbooks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", UUID(as_uuid=True), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.Text(), nullable=False, server_default="draft"),  # draft | published
        sa.Column("published_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("hero_image_path", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_yearbooks_org_season", "yearbooks", ["org_id", "season_id"], unique=True)
    op.create_index("ix_yearbooks_status", "yearbooks", ["status"])

    # Toggleable editorial sections (Presidents Report, Sponsors, Gallery, etc.)
    op.create_table(
        "yearbook_sections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("yearbook_id", UUID(as_uuid=True), sa.ForeignKey("yearbooks.id", ondelete="CASCADE"), nullable=False),
        # section_type: narrative | presidents_report | treasurers_report | sponsors |
        #               team_photos | gallery | farewells | new_members | custom
        sa.Column("section_type", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=True),
        sa.Column("ai_draft", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_yearbook_sections_yearbook", "yearbook_sections", ["yearbook_id"])

    # Honour board — club positions for the season (Captain, President, etc.)
    # Multiple rows per position_title = co-captains / co-holders
    op.create_table(
        "yearbook_honour_board",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("yearbook_id", UUID(as_uuid=True), sa.ForeignKey("yearbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position_title", sa.Text(), nullable=False),
        sa.Column("player_id", UUID(as_uuid=True), sa.ForeignKey("players.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name_override", sa.Text(), nullable=True),  # free-text for non-players
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_yearbook_honour_board_yearbook", "yearbook_honour_board", ["yearbook_id"])

    # Images — hero, team photos, gallery, sponsor logos
    op.create_table(
        "yearbook_images",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("yearbook_id", UUID(as_uuid=True), sa.ForeignKey("yearbooks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_path", sa.Text(), nullable=False),
        sa.Column("caption", sa.Text(), nullable=True),
        # image_type: hero | team_photo | gallery | sponsor_logo
        sa.Column("image_type", sa.Text(), nullable=False, server_default="gallery"),
        sa.Column("section_id", sa.Integer(), nullable=True),  # optional link to a yearbook_section
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_yearbook_images_yearbook", "yearbook_images", ["yearbook_id"])


def downgrade() -> None:
    op.drop_table("yearbook_images")
    op.drop_table("yearbook_honour_board")
    op.drop_table("yearbook_sections")
    op.drop_table("yearbooks")
