"""A theme belongs to ONE plan.

``club_strategic_pillars.plan_id``

Migration 232 made a pillar CLUB-scoped on the reasoning that a club's themes
are stable across plans, so the same few could serve the 12-month plan and the
5-year one. Running it as a tree proved that wrong in the worst way: a second
plan drew the first plan's themes, an objective filed under one of them read as
belonging to both, and deleting a theme from the second plan's tree deleted the
first plan's objectives — the club's real work — because it was the same row.

A plan owns its themes. A theme owns its objectives. There is no linkage
between one plan's hierarchy and another's.

The backfill has to keep every plan's tree intact, so a pillar whose objectives
span several plans is SPLIT: the row stays with one plan and a copy is made for
each of the others, with that plan's objectives re-pointed at its own copy. A
pillar with objectives in one plan simply joins it. A pillar with no objectives
at all cannot be attributed, so it keeps a NULL plan_id and shows as a theme no
plan has claimed, where it can be renamed onto a plan or deleted.

`ON DELETE CASCADE`: deleting a plan takes its themes with it, which is now
what a theme belonging to a plan means. The objectives under those themes are
governed by the plan delete's own `cascade` flag, unchanged.

Revision ID: 275
Revises: 274
"""
from alembic import op

revision = "275"
down_revision = "274"
branch_labels = None
depends_on = None


from app.services.pillar_plan_ddl import (  # noqa: E402
    PILLAR_PLAN_CLAIM_SQL,
    PILLAR_PLAN_SPLIT_SQL,
)


def upgrade() -> None:
    op.execute("""
        ALTER TABLE club_strategic_pillars
            ADD COLUMN IF NOT EXISTS plan_id UUID
            REFERENCES club_strategic_plans(id) ON DELETE CASCADE
    """)
    op.execute(PILLAR_PLAN_SPLIT_SQL)
    op.execute(PILLAR_PLAN_CLAIM_SQL)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_strategic_pillars_plan "
        "ON club_strategic_pillars(plan_id)"
    )


def downgrade() -> None:
    # The split rows cannot be re-merged without guessing which copy was the
    # original, so the column is simply dropped and every theme goes back to
    # being club-scoped. A club that ran the upgrade keeps its extra copies.
    op.execute("DROP INDEX IF EXISTS ix_club_strategic_pillars_plan")
    op.execute("ALTER TABLE club_strategic_pillars DROP COLUMN IF EXISTS plan_id")
