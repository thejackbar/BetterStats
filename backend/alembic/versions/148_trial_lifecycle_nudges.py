"""Trial lifecycle notifications + onboarding nudges (Phase 16, see
docs/self-serve-trial-onboarding-plan.md).

Adds ``trial_lifecycle_nudges``, a dedupe ledger for the daily scan in
app/services/trial_lifecycle.py: one row per (deterministic dedupe_key)
claimed just before an outbound nudge email is sent, so a club is never
emailed the same "your trial started/is ending/ended/converted" (or
onboarding nudge) more than once. Mirrors the ``twenty_links`` dedupe shape
already used for Twenty Task raising, but this ledger is platform-native
(no CRM dependency) since these emails go out regardless of whether Twenty
is configured.

Revision ID: 148
Revises: 147
Create Date: 2026-07-14
"""
from alembic import op


revision = '148'
down_revision = '147'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror) — see the
    # reasoning in migration 092: the schema is layered (dump + lifespan +
    # alembic), so a plain CREATE can hit an already-existing object and
    # abort `alembic upgrade head`, crash-looping the backend.
    op.execute("""
        CREATE TABLE IF NOT EXISTS trial_lifecycle_nudges (
            id UUID PRIMARY KEY,
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            module_key TEXT,
            nudge_type TEXT NOT NULL,
            dedupe_key TEXT NOT NULL UNIQUE,
            sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_trial_lifecycle_nudges_org "
        "ON trial_lifecycle_nudges(organisation_id, sent_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS trial_lifecycle_nudges")
