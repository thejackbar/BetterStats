"""BetterSelect Phase 0: persisted fixtures table.

BetterStats otherwise stores only *completed* games (a `games` row is written
only when a scorecard exists). BetterSelect's availability + team selection
need *forward* fixtures, so this adds a `fixtures` table.

Two sources:
  - 'playhq': synced from the partner API; the row id is the CA/PlayHQ game
    GUID, so a played fixture maps 1:1 to the eventual games.id row.
  - 'manual': admin-created (friendlies / pre-season) so lineups + social
    posts can be built without an official PlayHQ game; id is a fresh uuid4.

Revision ID: 043
Revises: 042
Create Date: 2026-05-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '043'
down_revision = '042'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fixtures",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("organisation_id", UUID(as_uuid=True),
                  sa.ForeignKey("organisations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grade_id", UUID(as_uuid=True),
                  sa.ForeignKey("grades.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.Text(), nullable=False, server_default="manual"),
        sa.Column("playhq_id", sa.Text(), nullable=True),
        sa.Column("label", sa.Text(), nullable=True),
        sa.Column("round", sa.Text(), nullable=True),
        sa.Column("played_on", sa.Date(), nullable=True),
        sa.Column("end_on", sa.Date(), nullable=True),
        sa.Column("start_time", sa.Text(), nullable=True),
        sa.Column("home_team", sa.Text(), nullable=True),
        sa.Column("away_team", sa.Text(), nullable=True),
        sa.Column("home_away", sa.Text(), nullable=True),
        sa.Column("opponent_name", sa.Text(), nullable=True),
        sa.Column("venue", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False, server_default="UPCOMING"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_fixtures_org", "fixtures", ["organisation_id"])
    op.create_index("ix_fixtures_org_played", "fixtures", ["organisation_id", "played_on"])


def downgrade() -> None:
    op.drop_index("ix_fixtures_org_played", table_name="fixtures")
    op.drop_index("ix_fixtures_org", table_name="fixtures")
    op.drop_table("fixtures")
