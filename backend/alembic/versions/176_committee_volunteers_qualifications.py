"""Committee Administration, Volunteer Management, Qualification tracking.

Three related but independent concerns, each a CORE capability (like Families
and Membership Types) — gated by a capability, not a paid module, and
nothing auto-seeded: a club adopts a starter catalogue (positions,
qualification types) or builds its own, same posture as everything else this
session.

Deliberately NOT built here (real, separate follow-on work, not silently
skipped): AGM nominations/elections/voting/motions/resolutions, a
"Committee Meeting Assistant", real file upload for club documents (this
ships link-based), automated expiry/renewal email reminders, and true
recurrence automation for annual tasks (a `is_recurring` flag + note only).

Reuses `fee_members` as "the person" for committee holders, volunteers and
qualification holders — the same unification point Membership Management and
Family/Household already use, rather than yet another person table.

- `committee_positions` / `committee_terms`: a position (President, …) and
  who's held it, when — supports history (ended_at NULL = current) without
  touching the existing, unrelated `club_committee` table (the PUBLIC
  website's simple "who's on committee" bio list, MANAGE_WEBSITE — a
  different concern serving a live public feature; not retrofitted here).
- `committee_tasks`: the Task Register + the "Calendar of Annual Tasks" from
  the brief, unified — they're the same shape (assigned, due date, status,
  category).
- `committee_documents`: a link-based registry (governance/policy docs live
  wherever the club already keeps them — Drive, Dropbox — this indexes them).
- `club_events`: the Club Calendar (AGM, working bees, sponsor functions…),
  distinct from cricket fixtures.
- `volunteer_profiles` / `volunteer_hours`: roles interested, availability,
  a hours ledger.
- `qualification_types` / `member_qualifications`: WWCC, First Aid, coach/
  umpire/scorer accreditation, with an expiry computed from a type's default
  validity period at the time a qualification is recorded.

Revision ID: 176
Revises: 175
Create Date: 2026-07-23
"""
from alembic import op


revision = '176'
down_revision = '175'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_positions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            responsibilities TEXT,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_committee_positions_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_positions_org ON committee_positions(organisation_id, is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_terms (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            position_id UUID NOT NULL REFERENCES committee_positions(id) ON DELETE CASCADE,
            member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            holder_name TEXT NOT NULL,
            started_at DATE NOT NULL DEFAULT CURRENT_DATE,
            ended_at DATE,
            handover_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_terms_position ON committee_terms(position_id, ended_at)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_terms_org ON committee_terms(organisation_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_tasks (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT NOT NULL DEFAULT 'operational',
            position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
            assigned_to_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            due_date DATE,
            status TEXT NOT NULL DEFAULT 'todo',
            is_recurring BOOLEAN NOT NULL DEFAULT false,
            recurrence_note TEXT,
            completed_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_tasks_org ON committee_tasks(organisation_id, status)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_tasks_due ON committee_tasks(organisation_id, due_date)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_documents (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'governance',
            url TEXT NOT NULL,
            position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_documents_org ON committee_documents(organisation_id, category)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS club_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            event_type TEXT NOT NULL DEFAULT 'other',
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ,
            location TEXT,
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_events_org ON club_events(organisation_id, starts_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_profiles (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            roles_interested JSONB NOT NULL DEFAULT '[]',
            available_days JSONB NOT NULL DEFAULT '[]',
            lives_nearby BOOLEAN NOT NULL DEFAULT false,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_volunteer_profiles_org_member UNIQUE (organisation_id, member_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS volunteer_hours (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            logged_date DATE NOT NULL DEFAULT CURRENT_DATE,
            hours NUMERIC(6,2) NOT NULL DEFAULT 0,
            activity TEXT,
            notes TEXT,
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_volunteer_hours_member ON volunteer_hours(member_id, logged_date DESC)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_volunteer_hours_org ON volunteer_hours(organisation_id, logged_date DESC)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS qualification_types (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            description TEXT,
            validity_months INTEGER,
            sort_order INTEGER NOT NULL DEFAULT 0,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_qualification_types_org_name UNIQUE (organisation_id, name)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_qualification_types_org ON qualification_types(organisation_id, is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS member_qualifications (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            qualification_type_id UUID NOT NULL REFERENCES qualification_types(id) ON DELETE CASCADE,
            obtained_at DATE NOT NULL DEFAULT CURRENT_DATE,
            expires_at DATE,
            certificate_ref TEXT,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_member_qualifications_member ON member_qualifications(member_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_member_qualifications_expiry ON member_qualifications(organisation_id, expires_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS member_qualifications")
    op.execute("DROP TABLE IF EXISTS qualification_types")
    op.execute("DROP TABLE IF EXISTS volunteer_hours")
    op.execute("DROP TABLE IF EXISTS volunteer_profiles")
    op.execute("DROP TABLE IF EXISTS club_events")
    op.execute("DROP TABLE IF EXISTS committee_documents")
    op.execute("DROP TABLE IF EXISTS committee_tasks")
    op.execute("DROP TABLE IF EXISTS committee_terms")
    op.execute("DROP TABLE IF EXISTS committee_positions")
