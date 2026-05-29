"""BetterSelect Phase 3: fixture lineups (team selection).

A lineup row = a player picked for a fixture. Per-fixture by design: the same
player can appear in two fixtures on the same weekend (the "shared player"
split case) — any cross-fixture rule lives in the app layer, not the schema.

Keyed (fixture_id, player_id). batting_order is the selection slot (1..n,
nullable until ordered). is_captain / is_wicket_keeper mirror game_appearances.

Revision ID: 049
Revises: 048
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '049'
down_revision = '048'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fixture_lineups",
        sa.Column("fixture_id", UUID(as_uuid=True),
                  sa.ForeignKey("fixtures.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("player_id", UUID(as_uuid=True),
                  sa.ForeignKey("players.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("batting_order", sa.Integer(), nullable=True),
        sa.Column("is_captain", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("is_wicket_keeper", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("selected_by", UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fixture_lineups_fixture", "fixture_lineups", ["fixture_id"])
    op.create_index("ix_fixture_lineups_org", "fixture_lineups", ["organisation_id"])


def downgrade() -> None:
    op.drop_index("ix_fixture_lineups_org", table_name="fixture_lineups")
    op.drop_index("ix_fixture_lineups_fixture", table_name="fixture_lineups")
    op.drop_table("fixture_lineups")
