"""BetterCRM — hide a Kanban stage/column from the board without deleting it.

A deal can still be moved into/out of a hidden stage (the Stage dropdown in
the deal detail modal always lists every stage) — hiding only drops its
column from the board view, for a stage a user wants out of the way (e.g.
"Lost / Dormant") without losing the ability to file a deal there.

Revision ID: 183
Revises: 182
Create Date: 2026-07-24
"""
from alembic import op

revision = '183'
down_revision = '182'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE crm_stages ADD COLUMN IF NOT EXISTS hidden_from_board BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE crm_stages DROP COLUMN IF EXISTS hidden_from_board")
