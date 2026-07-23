"""AGM meetings/elections/motions, Events/Ticketing, Assets & Facilities.

Continues the Committee Administration arc (migration 176): meetings,
agenda items, motions and AGM nominations all live under the same
MANAGE_COMMITTEE capability and reuse committee_positions/committee_terms —
an elected nomination writes a real committee_terms row via the existing
start_term() (auto-closing whatever term was open), so an AGM result and
the Positions tab's history are the same data, not two records of the truth.

Events/Ticketing extends the existing club_events (migration 176) with
ticketing fields + a registrations table. Per direct investigation this
round: the existing per-club Square connection (BetterMerch) was authorised
with READ-ONLY scopes (ITEMS_READ/INVENTORY_READ/ORDERS_READ) — creating
Square Payment Links needs PAYMENTS_WRITE/ORDERS_WRITE, which would require
every already-connected club to re-authorise. That's a real, separate piece
of follow-on work, not done here — registration/capacity/QR-code management
is real and complete; a paid event today records the ticket price and an
`awaiting_payment` status the club reconciles by hand (same posture
BetterFees already uses for bank-statement reconciliation), with no online
payment collection yet.

Assets/Facilities is a NEW, separate core capability (MANAGE_ASSETS) —
general club property (grounds equipment, technology, furniture) is a
different concern from BetterMerch's retail/kit stock tracking
(merch_assets, a paid-module table), so it isn't retrofitted there, same
reasoning as committee_positions vs the public club_committee table.
maintenance_logs is shared between assets and facilities (both need a
service/inspection history) rather than duplicated per subject type.

Revision ID: 177
Revises: 176
Create Date: 2026-07-23
"""
from alembic import op


revision = '177'
down_revision = '176'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── AGM / regular meetings ────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS agenda_templates (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            items JSONB NOT NULL DEFAULT '[]',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_agenda_templates_org_name UNIQUE (organisation_id, name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_meetings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            meeting_type TEXT NOT NULL DEFAULT 'committee',
            scheduled_at TIMESTAMPTZ NOT NULL,
            location TEXT,
            status TEXT NOT NULL DEFAULT 'scheduled',
            minutes TEXT,
            agenda_template_id UUID REFERENCES agenda_templates(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_meetings_org ON committee_meetings(organisation_id, scheduled_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS meeting_attendance (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            status TEXT NOT NULL DEFAULT 'present',
            CONSTRAINT uq_meeting_attendance UNIQUE (meeting_id, member_id)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS meeting_agenda_items (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            proposed_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            position INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'proposed',
            outcome_notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_meeting_agenda_items_meeting ON meeting_agenda_items(meeting_id, position)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS meeting_motions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
            agenda_item_id UUID REFERENCES meeting_agenda_items(id) ON DELETE SET NULL,
            motion_type TEXT NOT NULL DEFAULT 'motion',
            description TEXT NOT NULL,
            proposed_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            seconded_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            votes_for INTEGER,
            votes_against INTEGER,
            votes_abstain INTEGER,
            outcome TEXT NOT NULL DEFAULT 'pending',
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_meeting_motions_meeting ON meeting_motions(meeting_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS agm_nominations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            meeting_id UUID NOT NULL REFERENCES committee_meetings(id) ON DELETE CASCADE,
            position_id UUID NOT NULL REFERENCES committee_positions(id) ON DELETE CASCADE,
            candidate_member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            nominated_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            seconded_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            votes_for INTEGER,
            status TEXT NOT NULL DEFAULT 'nominated',
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_agm_nominations_meeting ON agm_nominations(meeting_id, position_id)")

    # ── Events / Ticketing ────────────────────────────────────────────────────
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS is_ticketed BOOLEAN NOT NULL DEFAULT false")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS ticket_price_cents INTEGER NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS capacity INTEGER")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS registration_deadline TIMESTAMPTZ")
    op.execute("ALTER TABLE club_events ADD COLUMN IF NOT EXISTS registration_open BOOLEAN NOT NULL DEFAULT true")

    op.execute("""
        CREATE TABLE IF NOT EXISTS event_registrations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            event_id UUID NOT NULL REFERENCES club_events(id) ON DELETE CASCADE,
            full_name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            quantity INTEGER NOT NULL DEFAULT 1,
            amount_cents INTEGER NOT NULL DEFAULT 0,
            payment_status TEXT NOT NULL DEFAULT 'free',
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_event_registrations_event ON event_registrations(event_id)")

    # ── Assets / Facilities ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS facilities (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            facility_type TEXT NOT NULL DEFAULT 'other',
            description TEXT,
            key_location TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_facilities_org ON facilities(organisation_id, is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS facility_bookings (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            facility_id UUID NOT NULL REFERENCES facilities(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            starts_at TIMESTAMPTZ NOT NULL,
            ends_at TIMESTAMPTZ,
            booked_by_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            notes TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_facility_bookings_facility ON facility_bookings(facility_id, starts_at)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS club_assets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'other',
            asset_tag TEXT,
            purchase_cost NUMERIC(10,2),
            purchase_date DATE,
            condition TEXT NOT NULL DEFAULT 'good',
            status TEXT NOT NULL DEFAULT 'in_service',
            service_due_date DATE,
            replace_due_date DATE,
            facility_id UUID REFERENCES facilities(id) ON DELETE SET NULL,
            notes TEXT,
            is_active BOOLEAN NOT NULL DEFAULT true,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_assets_org ON club_assets(organisation_id, is_active)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS maintenance_logs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            subject_type TEXT NOT NULL,
            subject_id UUID NOT NULL,
            performed_at DATE NOT NULL DEFAULT CURRENT_DATE,
            description TEXT NOT NULL,
            cost NUMERIC(10,2),
            performed_by TEXT,
            next_due_date DATE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_maintenance_logs_subject ON maintenance_logs(subject_type, subject_id, performed_at DESC)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS maintenance_logs")
    op.execute("DROP TABLE IF EXISTS club_assets")
    op.execute("DROP TABLE IF EXISTS facility_bookings")
    op.execute("DROP TABLE IF EXISTS facilities")
    op.execute("DROP TABLE IF EXISTS event_registrations")
    op.execute("ALTER TABLE club_events DROP COLUMN IF EXISTS registration_open")
    op.execute("ALTER TABLE club_events DROP COLUMN IF EXISTS registration_deadline")
    op.execute("ALTER TABLE club_events DROP COLUMN IF EXISTS capacity")
    op.execute("ALTER TABLE club_events DROP COLUMN IF EXISTS ticket_price_cents")
    op.execute("ALTER TABLE club_events DROP COLUMN IF EXISTS is_ticketed")
    op.execute("DROP TABLE IF EXISTS agm_nominations")
    op.execute("DROP TABLE IF EXISTS meeting_motions")
    op.execute("DROP TABLE IF EXISTS meeting_agenda_items")
    op.execute("DROP TABLE IF EXISTS meeting_attendance")
    op.execute("DROP TABLE IF EXISTS committee_meetings")
    op.execute("DROP TABLE IF EXISTS agenda_templates")
