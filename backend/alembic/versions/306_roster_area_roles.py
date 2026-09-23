"""Operational areas hold several roles, and a shift is for one of them.

An operational area used to pair exactly ONE role ("the role that covers it")
with ONE gating qualification. A real Match Day area involves several — Umpires,
Scorers, Team Managers, the extra hands a junior fixture needs — and each of
those has its own gating qualification (an Umpire needs accreditation, a Scorer
needs nothing). The roster's intended shape is Department -> Area -> Role ->
Shift -> Volunteer, where each area may hold several roles and each role may have
several shifts. The single `required_role_id` on the area could not express that.

New tables/columns:
    roster_area_roles              — an area's role PALETTE: each role it can
                                     involve, paired with the qualification that
                                     gates that role. Plural form of the old
                                     area (role, qualification) pair.
    roster_shift_patterns.role_id  — the one role a repeating shift is FOR
    roster_shifts.role_id          — the one role a concrete shift is FOR
                                     (NULL = general help, no specific role)

The paid/volunteer split, the qualification block, the role-shortage demand and
the shift's role label all move from the AREA to the shift's own role.

`roster_areas.required_role_id` / `.required_qualification_type_id` are kept but
DEPRECATED — read only by the backfill below; a new area leaves them NULL and the
palette is the source of truth.

Backfill so existing rosters behave identically: every single-role area becomes a
one-entry palette, and its patterns/shifts inherit that role, so generation, the
qualification block, the paid derivation and the shortages are unchanged.

Mirrored idempotently in app/main.py lifespan (migration 306 block).

Revision ID: 306
Revises: 305
"""
from alembic import op

revision = "306"
down_revision = "305"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS roster_area_roles (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        area_id UUID NOT NULL REFERENCES roster_areas(id) ON DELETE CASCADE,
        role_id UUID NOT NULL REFERENCES club_roles(id) ON DELETE CASCADE,
        required_qualification_type_id UUID REFERENCES qualification_types(id) ON DELETE SET NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_roster_area_roles UNIQUE (area_id, role_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_roster_area_roles_area ON roster_area_roles(area_id)",
    "ALTER TABLE roster_shift_patterns ADD COLUMN IF NOT EXISTS role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL",
    "ALTER TABLE roster_shifts ADD COLUMN IF NOT EXISTS role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL",
    # Backfill — every existing single-role area becomes a one-entry palette, and
    # its patterns/shifts inherit that role. Idempotent: the unique index makes
    # the INSERT a no-op on a second run, and the UPDATEs only touch NULL rows.
    """
    INSERT INTO roster_area_roles (organisation_id, area_id, role_id, required_qualification_type_id, sort_order)
        SELECT organisation_id, id, required_role_id, required_qualification_type_id, 0
        FROM roster_areas
        WHERE required_role_id IS NOT NULL
        ON CONFLICT (area_id, role_id) DO NOTHING
    """,
    """
    UPDATE roster_shift_patterns p SET role_id = a.required_role_id
        FROM roster_areas a
        WHERE a.id = p.area_id AND p.role_id IS NULL AND a.required_role_id IS NOT NULL
    """,
    """
    UPDATE roster_shifts s SET role_id = a.required_role_id
        FROM roster_areas a
        WHERE a.id = s.area_id AND s.role_id IS NULL AND a.required_role_id IS NOT NULL
    """,
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    op.execute("ALTER TABLE roster_shifts DROP COLUMN IF EXISTS role_id")
    op.execute("ALTER TABLE roster_shift_patterns DROP COLUMN IF EXISTS role_id")
    op.execute("DROP TABLE IF EXISTS roster_area_roles CASCADE")
