"""Setup Wizard "doesn't apply" steps + persisted socials style.

Two additions from the same Setup Wizard review round:

- onboarding_wizard_state.na_steps — steps the admin marked "doesn't apply"
  (Connect Square for a club that doesn't use Square, historical import for
  a club whose history is all on PlayHQ…). Distinct from skipped_steps: a
  skip parks a step and it still reads as to-do everywhere; a not-applicable
  step drops out of the progress counts entirely. Same JSON-array-beside-
  completed_steps shape as migration 157, for the same reason.

- organisations.socials_style — the social post generator's Style choices
  (palette key, dark/light, font, background texture + colour overrides,
  saved custom palettes/designs), previously localStorage-only. Persisted
  per club so the look survives browsers and second admins, and so the
  wizard's socials_palette step can auto-detect completion.

Revision ID: 162
Revises: 161
Create Date: 2026-07-18
"""
from alembic import op


revision = '162'
down_revision = '161'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute(
        "ALTER TABLE onboarding_wizard_state "
        "ADD COLUMN IF NOT EXISTS na_steps JSON NOT NULL DEFAULT '[]'"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS socials_style JSONB"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE onboarding_wizard_state DROP COLUMN IF EXISTS na_steps")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS socials_style")
