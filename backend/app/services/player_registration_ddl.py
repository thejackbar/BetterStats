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

STATEMENTS_398: list[str] = [
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

DOWNGRADE_398: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS player_registration_enabled",
    "DROP TABLE IF EXISTS player_registrations",
]

# Migration 399: smart matching and playing details.
#
# ``matched_by``  how a claimed record was proven theirs: 'mobile' (the full mobile they typed is the
#                 one on the record), 'pin' (last four digits of the mobile on file) or 'admin' (an
#                 admin approved it). NULL for a new person and an unproven claim.
# ``playing``     what they said about their cricket: player_role, batting_hand, bowling_action,
#                 bowling_type, is_opening_batsman, is_overseas, overseas_country.
# ``applied``     the fields this registration wrote onto the player (labels), so the admin list can
#                 say what changed. Only empty fields are ever written.
STATEMENTS_399: list[str] = [
    "ALTER TABLE player_registrations ADD COLUMN IF NOT EXISTS matched_by TEXT",
    "ALTER TABLE player_registrations ADD COLUMN IF NOT EXISTS playing JSONB NOT NULL DEFAULT '{}'::jsonb",
    "ALTER TABLE player_registrations ADD COLUMN IF NOT EXISTS applied JSONB NOT NULL DEFAULT '[]'::jsonb",
]

# Run ONCE by Alembic 399, never by the lifespan. v9.152.0 left a claim that was proven with the
# PIN waiting for review. Those were signed in on the spot (the audit row says
# 'registration_claimed', written only after a PIN matched where the club had the PIN on), so they
# are matches, not requests: mark them approved and matched by PIN. Bounded to rows written before
# this release, so it can never touch a later one.
FIX_399: list[str] = [
    """
    UPDATE player_registrations r
       SET status = 'approved', matched_by = 'pin', updated_at = now()
     WHERE r.kind = 'claim' AND r.status = 'pending' AND r.matched_by IS NULL
       AND r.created_at < TIMESTAMPTZ '2026-11-26 00:00:00+00'
       AND EXISTS (SELECT 1 FROM organisations o
                    WHERE o.id = r.organisation_id AND o.availability_require_pin IS TRUE)
       AND EXISTS (SELECT 1 FROM audit_events a
                    WHERE a.organisation_id = r.organisation_id AND a.player_id = r.player_id
                      AND a.action = 'registration_claimed')
    """,
]

DOWNGRADE_399: list[str] = [
    "ALTER TABLE player_registrations DROP COLUMN IF EXISTS applied",
    "ALTER TABLE player_registrations DROP COLUMN IF EXISTS playing",
    "ALTER TABLE player_registrations DROP COLUMN IF EXISTS matched_by",
]

# Everything the lifespan (and football's schema mirror) runs on every boot.
STATEMENTS: list[str] = STATEMENTS_398 + STATEMENTS_399
DOWNGRADE: list[str] = DOWNGRADE_399 + DOWNGRADE_398
