"""The DDL behind Player Dashboard self-registration (migration 398), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``player_registrations``
    One row each time somebody who could not find their name on the Player Dashboard
    added themselves (``kind = 'new'``) or claimed an older record of theirs that the
    name list hides (``kind = 'claim'``). ``player_id`` is the players row they use:
    the one the registration created, or the one they claimed. The row is the club's
    record of who came forward and what they said, so it is never deleted: an admin
    archives it (``status = 'archived'``) and can restore it.

    status: ``pending`` (not yet reviewed), ``approved``, ``archived``.
    role: see ``services/player_registration.ROLES``.

``organisations.player_registration_enabled``
    The "Let people add themselves" switch on BetterStats > Player Dashboard. NULL
    reads as on, so the button appears for every club that has the dashboard.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS player_registrations (
        id UUID PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        player_id UUID REFERENCES players(id) ON DELETE SET NULL,
        kind TEXT NOT NULL DEFAULT 'new',
        role TEXT NOT NULL,
        first_name TEXT,
        last_name TEXT NOT NULL,
        email TEXT,
        phone TEXT,
        date_of_birth DATE,
        years_played TEXT,
        grades_played TEXT,
        notes TEXT,
        interests JSONB NOT NULL DEFAULT '[]'::jsonb,
        contact_consent BOOLEAN NOT NULL DEFAULT FALSE,
        status TEXT NOT NULL DEFAULT 'pending',
        admin_note TEXT,
        contacted_at TIMESTAMPTZ,
        reviewed_at TIMESTAMPTZ,
        reviewed_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_player_registrations_org ON player_registrations (organisation_id, created_at DESC)",
    "CREATE INDEX IF NOT EXISTS ix_player_registrations_player ON player_registrations (player_id)",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS player_registration_enabled BOOLEAN",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS player_registration_enabled",
    "DROP TABLE IF EXISTS player_registrations",
]
