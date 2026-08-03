"""BetterClubManager — a managed Departments catalogue for Operational Areas.

roster_areas.department was free text; this adds a small per-club catalogue so
Departments can be CRUD'd and seeded (a Starter Pack) and the Operational Area
form can pick one from a dropdown. The area still stores its department as text
(non-breaking — existing areas keep working); the catalogue just feeds the
dropdown and lets a rename cascade to matching areas.

New table:
    roster_departments — org-scoped {name, sort_order, is_active}

Mirrored idempotently in app/main.py lifespan (migration 211 block).
"""
from alembic import op

revision = "211"
down_revision = "210"
branch_labels = None
depends_on = None

STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS roster_departments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        sort_order INTEGER NOT NULL DEFAULT 0,
        is_active BOOLEAN NOT NULL DEFAULT TRUE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_roster_departments_org_name UNIQUE (organisation_id, name)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_roster_departments_org ON roster_departments(organisation_id, is_active)",
]


def upgrade():
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade():
    op.execute("DROP TABLE IF EXISTS roster_departments CASCADE")
