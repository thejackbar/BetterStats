"""The DDL behind a player updating their own contact details (migration 356), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``players.address_line1 / suburb / state / postcode``
    Where the person lives, as they typed it. Plain text, all optional.
``players.emergency_contact_name / emergency_contact_phone``
    Who to call. Plain text, optional.

Email and mobile already live on ``players`` (``email``, ``phone``). Nothing here
is ever read by a public route: the only readers are the signed-in player's own
details screen and the club's admin profile.
"""

COLUMNS: tuple[str, ...] = (
    "address_line1", "suburb", "state", "postcode",
    "emergency_contact_name", "emergency_contact_phone",
)

STATEMENTS: list[str] = [
    f"ALTER TABLE players ADD COLUMN IF NOT EXISTS {c} TEXT" for c in COLUMNS
]

DOWNGRADE: list[str] = [
    f"ALTER TABLE players DROP COLUMN IF EXISTS {c}" for c in COLUMNS
]
