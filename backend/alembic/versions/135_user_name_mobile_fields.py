"""Add first_name/last_name/mobile_number to users.

The self-serve trial registration admin-details form (Phase 4, see
docs/self-serve-trial-onboarding-plan.md) collects these, but the existing
`users` table only ever had a single `display_name` and no phone field at all —
nothing downstream reads first_name/last_name/mobile_number yet. Nullable and
additive; existing users are entirely unaffected.

Revision ID: 135
Revises: 134
Create Date: 2026-07-13
"""
from alembic import op


revision = '135'
down_revision = '134'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS first_name TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS last_name TEXT")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS mobile_number TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS mobile_number")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS last_name")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS first_name")
