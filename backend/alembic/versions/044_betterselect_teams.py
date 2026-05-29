"""BetterSelect Phase 1: teams + player attributes.

- New `teams` table: first-class club teams (BetterStats otherwise only has
  team names as strings on games). Seeded from appearance data and/or created
  by hand.
- `fixtures.team_id`: optional link from a fixture to a team.
- Player attribute columns for the admin-managed BetterSelect model:
  email, phone, skill_positions (selection soft-sort), status (active/inactive).
  No player->team assignment: the model is club-wide.

Revision ID: 044
Revises: 043
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = '044'
down_revision = '043'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("grade_id", UUID(as_uuid=True),
                  sa.ForeignKey("grades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("default_formation", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("playhq_id", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("organisation_id", "name", name="uq_team_org_name"),
    )
    op.create_index("ix_teams_org", "teams", ["organisation_id"])

    op.add_column("fixtures", sa.Column("team_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_fixtures_team", "fixtures", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("players", sa.Column("email", sa.Text(), nullable=True))
    op.add_column("players", sa.Column("phone", sa.Text(), nullable=True))
    op.add_column(
        "players",
        sa.Column("skill_positions", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
    )
    op.add_column(
        "players",
        sa.Column("status", sa.Text(), nullable=False, server_default="active"),
    )


def downgrade() -> None:
    op.drop_column("players", "status")
    op.drop_column("players", "skill_positions")
    op.drop_column("players", "phone")
    op.drop_column("players", "email")
    op.drop_constraint("fk_fixtures_team", "fixtures", type_="foreignkey")
    op.drop_column("fixtures", "team_id")
    op.drop_index("ix_teams_org", table_name="teams")
    op.drop_table("teams")
