"""The DDL behind the club block list (migration 386), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``registration_blocks`` is a list of things BetterCricket will not serve. A row
is never deleted: lifting a block stamps ``lifted_at`` and the row stays as the
record of who decided what and why.

``kind``
    ``org_id``       a registered club (``organisations.id``): its members cannot
                     sign in and their open sessions stop working.
    ``ca_org_id``    a Cricket Australia / PlayHQ organisation id: that club cannot
                     be registered.
    ``club_name``    a club name, stored normalised (see
                     ``services/registration_blocks.normalise_name``): a club of
                     that name cannot be registered, whatever id it is picked with.
    ``email``        one address that cannot start a registration.
    ``email_domain`` everything at one domain (stored without the ``@``).

``reason`` is for staff only and is never sent to the person who is refused.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS registration_blocks (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        kind TEXT NOT NULL,
        value TEXT NOT NULL,
        reason TEXT,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        lifted_at TIMESTAMPTZ,
        lifted_by TEXT
    )
    """,
    # One live block per (kind, value); a lifted one does not count, so the same
    # thing can be blocked again later.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_registration_blocks_live
    ON registration_blocks (kind, value) WHERE lifted_at IS NULL
    """,
]

DOWNGRADE: list[str] = [
    "DROP INDEX IF EXISTS uq_registration_blocks_live",
    "DROP TABLE IF EXISTS registration_blocks",
]
