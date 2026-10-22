"""The DDL behind showing a "Player Page" button on the club's public site (migration 355), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``organisations.availability_show_on_site``
    On by default, which is every existing club: a club with the self-service
    link enabled gets the button beside Admin on its public site, and a club that
    does not want the link public turns it off in the BetterSelect link panel.
    The link itself is unchanged and still works wherever the club pinned it.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS availability_show_on_site BOOLEAN NOT NULL DEFAULT TRUE",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS availability_show_on_site",
]
