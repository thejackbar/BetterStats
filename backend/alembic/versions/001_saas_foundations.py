"""SaaS foundations: extend organisations, users; add club_memberships; player display_name_override

Revision ID: 001_saas_foundations
Revises:
Create Date: 2026-05-08

"""
from alembic import op
import sqlalchemy as sa

revision = "001_saas_foundations"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- organisations ---
    op.add_column("organisations", sa.Column("slug", sa.Text(), nullable=True))
    op.add_column("organisations", sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("organisations", sa.Column("primary_color", sa.Text(), server_default="#16c784", nullable=True))
    op.add_column("organisations", sa.Column("accent_color", sa.Text(), server_default="#243352", nullable=True))
    op.add_column("organisations", sa.Column("logo_url", sa.Text(), nullable=True))
    op.add_column("organisations", sa.Column("hero_image_url", sa.Text(), nullable=True))
    op.add_column("organisations", sa.Column("theme_mode", sa.Text(), server_default="auto", nullable=True))
    op.add_column("organisations", sa.Column("contact_email", sa.Text(), nullable=True))
    op.add_column(
        "organisations",
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=True),
    )

    # --- users ---
    op.add_column("users", sa.Column("username", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("display_name", sa.Text(), nullable=True))
    op.add_column("users", sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column("users", sa.Column("failed_login_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("users", sa.Column("locked_until", sa.TIMESTAMP(timezone=True), nullable=True))
    op.add_column(
        "users",
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=True),
    )
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=True)

    # --- club_memberships ---
    op.create_table(
        "club_memberships",
        sa.Column(
            "id",
            sa.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "club_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("organisations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.Text(), server_default="club_admin", nullable=False),
        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            server_default=sa.func.now(),
            nullable=True,
        ),
        sa.UniqueConstraint("club_id", "user_id", name="uq_club_membership"),
    )

    # --- players ---
    op.add_column("players", sa.Column("display_name_override", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("players", "display_name_override")
    op.drop_table("club_memberships")
    op.drop_column("users", "updated_at")
    op.drop_column("users", "locked_until")
    op.drop_column("users", "failed_login_count")
    op.drop_column("users", "last_login_at")
    op.drop_column("users", "display_name")
    op.drop_column("users", "username")
    op.alter_column("users", "email", existing_type=sa.Text(), nullable=False)
    op.drop_column("organisations", "updated_at")
    op.drop_column("organisations", "contact_email")
    op.drop_column("organisations", "theme_mode")
    op.drop_column("organisations", "hero_image_url")
    op.drop_column("organisations", "logo_url")
    op.drop_column("organisations", "accent_color")
    op.drop_column("organisations", "primary_color")
    op.drop_column("organisations", "is_active")
    op.drop_column("organisations", "slug")
