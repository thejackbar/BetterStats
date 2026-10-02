"""DDL for hiding a player at their own request (migration 316).

THE ONE COPY. Both alembic (versions/316_player_privacy_request.py) and the
lifespan mirror in main.py run this same list, in this order. Every statement
is idempotent, because the lifespan re-runs the whole list on every boot.

Three nullable columns on ``players`` and nothing else. ``is_public`` (migration
265) already hides a player from every public surface; these record that it was
the PERSON who asked, so the answer to "why is this player hidden" is on the
row, and so a club admin cannot quietly switch it back on.

  - ``privacy_hidden_at`` is the marker. NULL means nobody asked. A row is
    never deleted: a deleted player is simply re-created by the next sync, and
    the club's own records of the matches they played still need the row.
  - ``privacy_hidden_by`` and ``privacy_hidden_reason`` say who recorded it and
    what the request was, in the words of whoever handled it.

One small table, ``player_privacy_suppressions``, keyed on the Cricket Australia
participant id. A person has one row PER CLUB (the id is per-club), and a club
that joins later, or a fixture a different club syncs, mints a NEW row for the
same person. The suppression is what stops that new row appearing publicly:
every creator that knows the participant id checks it
(``services/player_privacy.protect_new_player``).
"""

STATEMENTS: list[str] = [
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_at TIMESTAMPTZ",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_by TEXT",
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_hidden_reason TEXT",
    """CREATE TABLE IF NOT EXISTS player_privacy_suppressions (
        grassroots_id TEXT PRIMARY KEY,
        reason TEXT,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS player_privacy_suppressions",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_reason",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_by",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_at",
]
