"""BetterClubManager Roster — the weekly volunteer roster.

New tables:
    roster_areas           — operational areas (a slice of club work) with the
                             role that covers it and the qualification that gates it
    roster_shift_patterns  — the repeating weekly template per area
    roster_weeks           — one published/draft week
    roster_shifts          — the concrete shifts for a week, each optionally
                             assigned to a member, with derived warnings
    roster_settings        — per-club rostering settings (enforce quals, weekly cap)

Column additions:
    volunteer_profiles     — max_shifts_per_week (per-person weekly cap)

Assignments are validated by a rules engine (services/roster.py); everything
else (coverage, per-person load, candidate ranking) is derived on read.

Mirrored idempotently in app/main.py lifespan (migration 208 block).
"""
from alembic import op

revision = "208"
down_revision = "207"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS roster_areas (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        department TEXT,
        color TEXT,
        required_role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL,
        required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_roster_areas_org ON roster_areas(organisation_id, is_active)",
    """
    CREATE TABLE IF NOT EXISTS roster_shift_patterns (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
        day_of_week INTEGER NOT NULL,
        start_time NUMERIC(4,2) NOT NULL,
        end_time NUMERIC(4,2) NOT NULL,
        headcount INTEGER NOT NULL DEFAULT 1,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_roster_shift_patterns_area ON roster_shift_patterns(area_id)",
    """
    CREATE TABLE IF NOT EXISTS roster_weeks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        week_start DATE NOT NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_roster_weeks_org_week UNIQUE (organisation_id, week_start)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS roster_shifts (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        roster_week_id UUID NOT NULL REFERENCES roster_weeks(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
        day_of_week INTEGER NOT NULL,
        start_time NUMERIC(4,2) NOT NULL,
        end_time NUMERIC(4,2) NOT NULL,
        assignee_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
        warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_roster_shifts_week ON roster_shifts(roster_week_id)",
    """
    CREATE TABLE IF NOT EXISTS roster_settings (
        organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
        enforce_qualifications BOOLEAN NOT NULL DEFAULT TRUE,
        weekly_shift_cap INTEGER NOT NULL DEFAULT 0,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "ALTER TABLE volunteer_profiles ADD COLUMN IF NOT EXISTS max_shifts_per_week INTEGER",
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    for tbl in ("roster_shifts", "roster_weeks", "roster_shift_patterns", "roster_areas", "roster_settings"):
        op.execute(f"DROP TABLE IF EXISTS {tbl} CASCADE")
    op.execute("ALTER TABLE volunteer_profiles DROP COLUMN IF EXISTS max_shifts_per_week")
