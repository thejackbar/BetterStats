"""Roles & Activities, Event Types, and Volunteer/Qualification/Events/Bookings/
Club-Diary extensions for BetterClubManager.

New catalogue tables (club-defined, opt-in starter sets — nothing auto-seeded):
    club_role_types / club_roles          — the volunteer role taxonomy
    club_activity_types / club_activities — what logged hours were spent on
    club_event_types                      — event kinds (+ committee-only)
    volunteer_roles / qualification_roles — link a member/qualification to roles
    club_diary_task_dependencies          — task-before-task ordering (Gantt)

Column additions:
    club_events        — event_type_id, organiser_member_id, organiser_name
    volunteer_hours    — activity_id
    facility_bookings  — contact_name/email/mobile, owner_member_id, owner_name
    club_diary_categories        — color
    club_diary_task_definitions  — responsibility_role_id, third_party, budget_estimate
    club_diary_task_occurrences  — assigned_to_role_id, start_date, percent_complete,
                                   estimated_completion_date, third_party,
                                   budget_estimate, actual_expenditure

Mirrored idempotently in app/main.py lifespan (migration 197 block).
"""
from alembic import op

revision = "197"
down_revision = "196"
branch_labels = None
depends_on = None


def upgrade():
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_role_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_role_types_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_roles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            role_type_id UUID REFERENCES club_role_types(id) ON DELETE SET NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_roles_org_title UNIQUE (organisation_id, title)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_roles_org ON club_roles(organisation_id, is_active)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_activity_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_activity_types_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_activities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            activity_type_id UUID REFERENCES club_activity_types(id) ON DELETE SET NULL,
            description TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_activities_org_title UNIQUE (organisation_id, title)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_activities_org ON club_activities(organisation_id, is_active)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_roles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_volunteer_roles_member_role UNIQUE (member_id, role_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_volunteer_roles_member ON volunteer_roles(member_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS qualification_roles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            qualification_id UUID NOT NULL REFERENCES member_qualifications(id) ON DELETE CASCADE,
            role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_qualification_roles_qual_role UNIQUE (qualification_id, role_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_qualification_roles_qual ON qualification_roles(qualification_id)")
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_event_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            is_committee_only BOOLEAN NOT NULL DEFAULT FALSE,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT TRUE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_event_types_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_diary_task_dependencies (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
            depends_on_definition_id UUID NOT NULL REFERENCES club_diary_task_definitions(id) ON DELETE CASCADE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_club_diary_task_dependency UNIQUE (definition_id, depends_on_definition_id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_diary_task_deps_def ON club_diary_task_dependencies(definition_id)")

    # ── Column additions ──
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS event_type_id UUID REFERENCES club_event_types(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS organiser_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS organiser_name TEXT")

    op.execute("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS activity_id UUID REFERENCES club_activities(id) ON DELETE SET NULL")

    op.execute("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_name TEXT")
    op.execute("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_email TEXT")
    op.execute("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS contact_mobile TEXT")
    op.execute("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS owner_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE facility_bookings ADD COLUMN IF NOT EXISTS owner_name TEXT")

    op.execute("ALTER TABLE club_diary_categories ADD COLUMN IF NOT EXISTS color TEXT")

    op.execute("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS responsibility_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS third_party TEXT")
    op.execute("ALTER TABLE club_diary_task_definitions ADD COLUMN IF NOT EXISTS budget_estimate NUMERIC(10, 2)")

    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS assigned_to_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS start_date DATE")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS percent_complete INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS estimated_completion_date DATE")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS third_party TEXT")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS budget_estimate NUMERIC(10, 2)")
    op.execute("ALTER TABLE club_diary_task_occurrences ADD COLUMN IF NOT EXISTS actual_expenditure NUMERIC(10, 2)")


def downgrade():
    for col in ("assigned_to_role_id", "start_date", "percent_complete", "estimated_completion_date",
                "third_party", "budget_estimate", "actual_expenditure"):
        op.execute(f"ALTER TABLE club_diary_task_occurrences DROP COLUMN IF EXISTS {col}")
    for col in ("responsibility_role_id", "third_party", "budget_estimate"):
        op.execute(f"ALTER TABLE club_diary_task_definitions DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE club_diary_categories DROP COLUMN IF EXISTS color")
    for col in ("contact_name", "contact_email", "contact_mobile", "owner_member_id", "owner_name"):
        op.execute(f"ALTER TABLE facility_bookings DROP COLUMN IF EXISTS {col}")
    op.execute("ALTER TABLE volunteer_hours DROP COLUMN IF EXISTS activity_id")
    for col in ("event_type_id", "organiser_member_id", "organiser_name"):
        op.execute(f"ALTER TABLE club_events DROP COLUMN IF EXISTS {col}")
    for tbl in ("club_diary_task_dependencies", "club_event_types", "qualification_roles",
                "volunteer_roles", "club_activities", "club_activity_types", "club_roles", "club_role_types"):
        op.execute(f"DROP TABLE IF EXISTS {tbl}")
