"""Strategic plans as a record, not a typed-in label.

An objective already carried a ``plan`` — but as free text on each row, so
"Strategic Plan 2026" and "Strategic plan 2026" were two different plans, a
plan could not be renamed, and there was nothing to hang a plan's own dates or
description off. This gives the plan a row of its own and points objectives at
it.

An objective also gains what a club actually plans with: when it is due, who
owns it, and what it is allowed to cost. Those three sat on the ACTIONS serving
an objective and nowhere on the objective itself, so an objective with no
actions yet had no owner, no date and no budget.

A motion can now point at an objective too. An action already could, which
meant "the committee resolved to do this" and "someone is doing it" reported
against the plan differently.

The old ``club_objectives.plan`` text is backfilled into real plan rows and
then left alone as history. Nothing reads it after this.

Revision ID: 230
Revises: 229
"""
from alembic import op

revision = "230"
down_revision = "229"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_strategic_plans (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            -- The years the plan runs over, e.g. 2026 → 2029. Both optional:
            -- plenty of clubs run a plan with no end date written down.
            start_year INTEGER,
            end_year INTEGER,
            status TEXT NOT NULL DEFAULT 'active',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_strategic_plans_org "
        "ON club_strategic_plans(organisation_id, status)"
    )

    for col, ddl in [
        ("plan_id", "UUID REFERENCES club_strategic_plans(id) ON DELETE SET NULL"),
        ("due_date", "DATE"),
        ("owner_member_id", "UUID REFERENCES fee_members(id) ON DELETE SET NULL"),
        ("budget", "NUMERIC(12,2)"),
    ]:
        op.execute(f"ALTER TABLE club_objectives ADD COLUMN IF NOT EXISTS {col} {ddl}")
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_objectives_plan ON club_objectives(plan_id)")

    # A motion serves the plan the same way an action does.
    op.execute(
        "ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS "
        "objective_id UUID REFERENCES club_objectives(id) ON DELETE SET NULL"
    )

    # ── Backfill the typed-in plan names into real rows ──────────────────────
    #
    # Grouped case-insensitively on the trimmed name, so a club that typed the
    # same plan two slightly different ways ends up with one plan rather than
    # two that then have to be merged by hand. The name kept is the first
    # spelling, which is as good a choice as any and at least is one of theirs.
    #
    # The NOT EXISTS is what makes it safe to run twice, and it HAS to be that
    # rather than ON CONFLICT: this whole file is mirrored into main.py's
    # lifespan and re-runs on every boot, and there is no unique constraint on
    # (org, name) for a conflict clause to fire against — deliberately, since a
    # club is entitled to name two plans the same thing if it wants to.
    op.execute("""
        INSERT INTO club_strategic_plans (organisation_id, name)
        SELECT o.organisation_id, MIN(BTRIM(o.plan))
        FROM club_objectives o
        WHERE o.plan IS NOT NULL AND BTRIM(o.plan) <> ''
          AND NOT EXISTS (
              SELECT 1 FROM club_strategic_plans p
              WHERE p.organisation_id = o.organisation_id
                AND LOWER(BTRIM(p.name)) = LOWER(BTRIM(o.plan))
          )
        GROUP BY o.organisation_id, LOWER(BTRIM(o.plan))
    """)
    op.execute("""
        UPDATE club_objectives o
        SET plan_id = p.id
        FROM club_strategic_plans p
        WHERE o.plan_id IS NULL
          AND o.plan IS NOT NULL
          AND p.organisation_id = o.organisation_id
          AND LOWER(BTRIM(p.name)) = LOWER(BTRIM(o.plan))
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE meeting_motions DROP COLUMN IF EXISTS objective_id")
    op.execute("DROP INDEX IF EXISTS ix_club_objectives_plan")
    for col in ("plan_id", "due_date", "owner_member_id", "budget"):
        op.execute(f"ALTER TABLE club_objectives DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS club_strategic_plans")
