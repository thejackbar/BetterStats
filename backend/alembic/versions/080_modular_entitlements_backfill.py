"""Modular entitlements: backfill each club's module list from its old tier.

The platform moved from Good/Better/Best tier bundles to a per-module model. A
club's ``module_overrides`` is now the single source of truth for which modules
it holds (see app/auth/modules.py). Existing clubs only had their modules
implied by their tier, so this writes each club's tier modules into
``module_overrides`` (merged with any modules already granted à la carte), so
no club loses access when the tier map goes away.

  good   -> none (Core only)
  better -> select, socials
  best   -> select, socials, fees, iq, comms

Data-only and idempotent: re-running merges the same set. The ``tier`` column is
left in place (deprecated, no longer read) so the original plan stays on record.

Revision ID: 080
Revises: 079
Create Date: 2026-06-11

"""
import json

import sqlalchemy as sa
from alembic import op


revision = '080'
down_revision = '079'
branch_labels = None
depends_on = None


TIER_MODULES = {
    'good': [],
    'better': ['select', 'socials'],
    'best': ['select', 'socials', 'fees', 'iq', 'comms'],
}


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(sa.text(
        "SELECT id, tier, module_overrides FROM organisations"
    )).mappings().all()
    for r in rows:
        existing = r["module_overrides"] or []
        if isinstance(existing, str):
            existing = json.loads(existing)
        merged = sorted(set(existing) | set(TIER_MODULES.get(r["tier"] or "good", [])))
        if set(merged) != set(existing):
            conn.execute(
                sa.text("UPDATE organisations SET module_overrides = CAST(:m AS jsonb) WHERE id = :id"),
                {"m": json.dumps(merged), "id": r["id"]},
            )


def downgrade() -> None:
    # No-op. The deprecated ``tier`` column still holds each club's original
    # plan, so the mapping can be recomputed if ever needed. We don't strip the
    # backfilled modules on downgrade because they're now indistinguishable from
    # modules granted à la carte.
    pass
