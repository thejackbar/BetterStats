"""The DDL behind the Player Dashboard switch for clubs without BetterSelect (migration 372), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``organisations.player_dashboard_enabled``
    The Player Dashboard switch (Player Cards, season, fantasy, fees), set in BetterStats. Nullable
    on purpose: NULL means "never chosen" and reads as the old rule (a club with BetterSelect follows
    ``availability_self_service_enabled``, a club without it is on unless it hid the page from its
    site), so no existing link changes. An explicit true or false is the club's own choice and is
    independent of the BetterSelect availability switch.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS player_dashboard_enabled BOOLEAN",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS player_dashboard_enabled",
]
