"""The DDL behind a net session's own check-in link and squad (migration 335), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``net_sessions.checkin_token``
    A token for THIS session's check-in link. The club-wide link
    (``organisations.net_checkin_token``) checks a player into every session
    that is live, which is wrong for a club running seniors on Tuesday and
    juniors on Thursday, or two sessions on one night: a QR code printed for one
    session must check people into that session only. NULL until the link is
    first asked for (older sessions), then fixed; unique.

``net_sessions.squad_team_ids``
    The squads this session is for. NULL or empty = everyone, which is every
    existing session. When set, the self check-in list for the session's own
    link shows only members of those squads.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS checkin_token TEXT",
    "ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS squad_team_ids UUID[]",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_net_sessions_checkin_token "
    "ON net_sessions (checkin_token) WHERE checkin_token IS NOT NULL",
]

DOWNGRADE: list[str] = [
    "DROP INDEX IF EXISTS uq_net_sessions_checkin_token",
    "ALTER TABLE net_sessions DROP COLUMN IF EXISTS squad_team_ids",
    "ALTER TABLE net_sessions DROP COLUMN IF EXISTS checkin_token",
]
