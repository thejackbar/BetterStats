"""BetterComms monthly cap + reset every club to the sandbox tier

Two changes:

  * Adds ``organisations.comms_monthly_cap`` — a per-club monthly send ceiling
    on top of the daily cap (NULL = use the global default, 0 = no monthly
    limit). A super admin sets it when onboarding a club on BetterAdmin.

  * Resets every club back to the ``sandbox`` tier. Migration 125 blanket-set
    all existing clubs to ``production`` to avoid throttling live clubs on
    deploy, but that put clubs on the raised limit without anyone requesting it.
    The intended model is that a club EARNS production by requesting a lift a
    super admin approves — so we start everyone in sandbox. The outreach org is
    uncapped regardless of tier, so it is untouched in spirit (harmless if reset).

The reset lives ONLY in this migration (a one-time correction), NOT in the
main.py lifespan mirror — mirroring it would undo a super admin's future
production approvals on every boot. The column add IS mirrored idempotently.

Revision ID: 129
Revises: 128
"""
from alembic import op

revision = "129"
down_revision = "128"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_monthly_cap INTEGER")
    # One-time correction: undo migration 125's blanket production set. A club
    # earns production by request + super-admin approval. Suspended clubs stay
    # suspended (the breaker put them there); only production → sandbox flips.
    op.execute("UPDATE organisations SET comms_tier = 'sandbox' "
               "WHERE comms_tier = 'production' "
               "AND COALESCE(is_marketing_outreach, false) = false")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS comms_monthly_cap")
