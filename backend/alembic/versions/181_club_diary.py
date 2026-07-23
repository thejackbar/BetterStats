"""Club Diary — annual/recurring compliance & maintenance task calendar.

A NEW core capability (MANAGE_CLUB_DIARY), separate from Committee
Administration's existing task register (committee_tasks) — that table is a
single mutable row per task with no per-period history, whereas the whole
point of a Club Diary is "what did we do about this exact recurring task
last year, and the year before that." So this is a definition/occurrence
split instead:

- club_diary_categories — club-defined (not the fixed committee_tasks
  category list), so a club can group tasks its own way (Compliance, Tax,
  Ground & Equipment, whatever they call it).
- club_diary_task_definitions — the recurring task itself (title,
  frequency, suggested month, a default assignee), created either by hand
  or from the opt-in starter template (STARTER_DIARY_TASKS in
  services/club_diary.py — nothing is auto-seeded).
- club_diary_task_occurrences — one row per period (a year, or a year+quarter
  for a quarterly task) against a definition — due date, status, notes,
  who actually did it, completed_at. Querying every occurrence for one
  definition, newest first, IS the "history of previous year activities"
  the feature exists for. Occurrences are created lazily (on-demand, when a
  period's board is first viewed) rather than by a cron job — see
  services/club_diary.py::ensure_occurrences_for_period.

Revision ID: 181
Revises: 180
Create Date: 2026-07-23
"""
from alembic import op

revision = '181'
down_revision = '180'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_diary_categories (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_diary_categories_org_name UNIQUE (organisation_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS club_diary_task_definitions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            category_id UUID REFERENCES club_diary_categories(id) ON DELETE SET NULL,
            title TEXT NOT NULL,
            description TEXT,
            frequency TEXT NOT NULL DEFAULT 'annual',
            default_month INTEGER,
            default_assignee_position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
            default_assignee_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_diary_definitions_org_title UNIQUE (organisation_id, title)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_diary_definitions_org ON club_diary_task_definitions(organisation_id, is_active)"
    )

    op.execute("""
        CREATE TABLE IF NOT EXISTS club_diary_task_occurrences (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
            period_label TEXT NOT NULL,
            due_date DATE,
            status TEXT NOT NULL DEFAULT 'pending',
            assigned_to_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            notes TEXT,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_diary_occurrence_period UNIQUE (definition_id, period_label)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_diary_occurrences_org ON club_diary_task_occurrences(organisation_id, status)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_diary_occurrences_definition "
        "ON club_diary_task_occurrences(definition_id, period_label DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS club_diary_task_occurrences")
    op.execute("DROP TABLE IF EXISTS club_diary_task_definitions")
    op.execute("DROP TABLE IF EXISTS club_diary_categories")
