"""DDL for sponsor tiers and per-sponsor placements (migration 318).

THE ONE COPY. Both alembic (versions/318_sponsor_tiers.py) and the lifespan
mirror in main.py run this same list, in this order. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

  - ``org_sponsors.tier`` is one of major / gold / silver / supporter. Existing
    sponsors land on 'silver', which shows them exactly where they showed
    before (the bottom bar and every club page's sponsor list), so no club's
    public pages change because of an upgrade.
  - ``org_sponsors.placements`` holds only the spots a club has switched on or
    off by hand ({"dashboard": true, "bar": false}). NULL, or a missing key,
    means "follow the tier". What a sponsor shows on is DERIVED on read
    (services/sponsor_tiers.py), so changing a tier moves every sponsor that
    never had an override.
  - ``organisations.sponsor_tier_labels`` holds the club's own names for the
    four tiers ({"major": "Naming Partner"}). NULL means the stock names.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS tier TEXT NOT NULL DEFAULT 'silver'",
    "ALTER TABLE org_sponsors ADD COLUMN IF NOT EXISTS placements JSONB",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS sponsor_tier_labels JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS sponsor_tier_labels",
    "ALTER TABLE org_sponsors DROP COLUMN IF EXISTS placements",
    "ALTER TABLE org_sponsors DROP COLUMN IF EXISTS tier",
]
