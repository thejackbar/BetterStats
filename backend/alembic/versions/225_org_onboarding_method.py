"""Record HOW a club came to be onboarded, on the club itself.

The CRM deal has carried ``onboarding_method`` since migration 184, but a deal
is a sales artefact - it can be edited, archived, or never created at all when
Twenty/the pipeline is unavailable. Two things need the answer regardless:

  * ``services/trial_engagement.py`` scores a staff-performed registration lower
    than a club registering itself. It used to infer that from "does this club
    have a primary club admin", which only worked because the Super Admin "New
    Club" flow never created one. That flow now does, so the inference no longer
    holds and the fact has to be stored.
  * ``routers/onboarding_wizard.py`` auto-opens the setup wizard for a genuinely
    new trial club whose admin has never seen it - a condition that must never
    catch a long-established club, so it keys on this column being set.

Nullable, and left NULL for every club onboarded before this shipped: absent
means "unknown", not "neither". Values match the CRM deal's own vocabulary
(frontend/src/components/admin/crm/ui.jsx ONBOARDING_METHOD_OPTIONS):
``self_serve_trial`` | ``super_admin_trial`` | ``direct_subscriber`` | ``none``.

Revision ID: 225
Revises: 224
"""
from alembic import op

revision = "225"
down_revision = "224"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS onboarding_method TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS onboarding_method")
