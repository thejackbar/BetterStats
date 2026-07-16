"""Setup wizard: skipped_steps on onboarding_wizard_state.

The onboarding checklist modal (migration 140, Phase 15) grew into a full
step-by-step Setup Wizard (/admin/setup) covering the whole platform. Each
step can now be explicitly skipped as well as completed — a skipped step
counts as "addressed" for progress purposes but renders differently and can
be picked back up later. Stored as its own JSON array beside completed_steps
rather than a status map so the existing completed_steps consumers (and any
rows already carrying progress) keep working untouched.

Revision ID: 157
Revises: 156
Create Date: 2026-07-16
"""
from alembic import op


revision = '157'
down_revision = '156'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute(
        "ALTER TABLE onboarding_wizard_state "
        "ADD COLUMN IF NOT EXISTS skipped_steps JSON NOT NULL DEFAULT '[]'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE onboarding_wizard_state DROP COLUMN IF EXISTS skipped_steps")
