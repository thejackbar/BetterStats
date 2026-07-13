"""Add onboarding_wizard_state table.

Phase 15 (see docs/self-serve-trial-onboarding-plan.md) — the club onboarding
wizard's per-club progress. See app/models/db.py::OnboardingWizardState for
the column-by-column rationale.

Revision ID: 140
Revises: 139
Create Date: 2026-07-13
"""
from alembic import op


revision = '140'
down_revision = '139'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS onboarding_wizard_state (
            organisation_id UUID PRIMARY KEY REFERENCES organisations(id) ON DELETE CASCADE,
            completed_steps JSON NOT NULL DEFAULT '[]',
            dismissed_at TIMESTAMPTZ,
            sync_steps_shown_at TIMESTAMPTZ,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS onboarding_wizard_state")
