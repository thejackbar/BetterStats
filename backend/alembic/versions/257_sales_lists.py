"""Sales Workspace — Sales Lists.

A thin provenance/import layer, not a parallel data model. Assignment still
lives solely on ``crm_deals.owner_user_id`` (unchanged); call history, notes
and stage all still live on the deal. A Sales List is just "these clubs came
in together, from this source" — club history follows the club, not the
list, so a club can sit in several lists and its calls/notes/stage are the
same wherever it's viewed from.

- ``sales_lists`` — one row per import batch (a Wizard Clubs pull, a CRM
  export, a Club Directory selection, or a manual pick).
- ``sales_list_clubs`` — the many-to-many membership, unique per
  (list, club) so re-importing an overlapping selection is idempotent.

Revision ID: 257
Revises: 256
Create Date: 2026-08-15
"""
from alembic import op


revision = '257'
down_revision = '256'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales_lists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL,
            description TEXT,
            source_type TEXT NOT NULL DEFAULT 'manual',
            created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS sales_list_clubs (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sales_list_id UUID NOT NULL REFERENCES sales_lists(id) ON DELETE CASCADE,
            marketing_club_id UUID NOT NULL REFERENCES marketing_clubs(id) ON DELETE CASCADE,
            added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (sales_list_id, marketing_club_id)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_list_clubs_club ON sales_list_clubs(marketing_club_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_sales_list_clubs_list ON sales_list_clubs(sales_list_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS sales_list_clubs")
    op.execute("DROP TABLE IF EXISTS sales_lists")
