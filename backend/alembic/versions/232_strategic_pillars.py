"""Pillars, an owner that survives the AGM, and something to start from.

Three things, all optional, all serving the same problem: a volunteer committee
opening a blank strategic plan closes it again.

- `club_strategic_pillars` is the club's own small list of themes — on-field,
  finances, volunteers, facilities. Objectives point at one. It is club-scoped
  rather than plan-scoped ON PURPOSE: a club's pillars are stable across plans,
  so the same four serve the 12-month plan and the 5-year one, and "how is
  Financial Sustainability going" can be asked across both at once.

  A pillar is a GROUPING, not another level of the hierarchy. Plan → objective
  → action stays three deep; the pillar is a heading within a plan.

- `club_objectives.owner_position_id` lets a committee SEAT own an objective,
  not just a person, so ownership transfers at the AGM without anyone editing
  anything. The Club Diary already works this way
  (`club_diary_task_definitions.default_assignee_position_id`) and this is the
  same idea in the same shape.

Revision ID: 232
Revises: 231
"""
from alembic import op

revision = "232"
down_revision = "231"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_strategic_pillars (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_strategic_pillars_org "
        "ON club_strategic_pillars(organisation_id, is_active)"
    )
    for col, ddl in [
        ("pillar_id", "UUID REFERENCES club_strategic_pillars(id) ON DELETE SET NULL"),
        ("owner_position_id", "UUID REFERENCES committee_positions(id) ON DELETE SET NULL"),
    ]:
        op.execute(f"ALTER TABLE club_objectives ADD COLUMN IF NOT EXISTS {col} {ddl}")


def downgrade() -> None:
    for col in ("pillar_id", "owner_position_id"):
        op.execute(f"ALTER TABLE club_objectives DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS club_strategic_pillars")
