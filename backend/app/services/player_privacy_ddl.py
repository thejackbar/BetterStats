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

THE DATABASE ENFORCES IT TOO. The suppression belongs to the person, not to a
club, so it is enforced where every club's rows live. A BEFORE INSERT and a
BEFORE UPDATE trigger on ``players`` look the row's participant id up in the
suppression table and force it hidden: ``is_public`` false and the marker set.
That covers a creator nobody remembered to teach (an importer, a raw INSERT, a
code path written next year) and any attempt to switch a suppressed person back
on. The trigger forces rather than raises, so a sync or a merge never fails on
it. The backfill statement hides any row that predates the trigger. It cannot
help a row with no participant id (a hand-typed player): those are caught by
the name masking in ``services/privacy_scrub``.
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
    # to_jsonb(NEW) reads grassroots_id without naming the column, so the same
    # function loads on a database whose players table lacks it.
    """CREATE OR REPLACE FUNCTION player_privacy_enforce() RETURNS trigger AS $fn$
    DECLARE
        sup RECORD;
    BEGIN
        SELECT s.reason, s.created_by INTO sup
          FROM player_privacy_suppressions s
         WHERE s.grassroots_id IN (
                   LOWER(COALESCE(to_jsonb(NEW) ->> 'grassroots_id', '')),
                   LOWER(NEW.id::text))
         LIMIT 1;
        IF FOUND THEN
            NEW.is_public := FALSE;
            IF NEW.privacy_hidden_at IS NULL THEN
                NEW.privacy_hidden_at := NOW();
                NEW.privacy_hidden_by := COALESCE(sup.created_by, 'suppression');
                NEW.privacy_hidden_reason := sup.reason;
            END IF;
        END IF;
        RETURN NEW;
    END
    $fn$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_ins ON players",
    """CREATE TRIGGER player_privacy_enforce_ins BEFORE INSERT ON players
       FOR EACH ROW EXECUTE PROCEDURE player_privacy_enforce()""",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_upd ON players",
    """CREATE TRIGGER player_privacy_enforce_upd
       BEFORE UPDATE OF is_public, privacy_hidden_at, grassroots_id ON players
       FOR EACH ROW EXECUTE PROCEDURE player_privacy_enforce()""",
    # Rows that predate the trigger. Matches nothing once they are all marked.
    """UPDATE players p
          SET is_public = FALSE,
              privacy_hidden_at = COALESCE(p.privacy_hidden_at, NOW()),
              privacy_hidden_by = COALESCE(p.privacy_hidden_by, s.created_by, 'suppression'),
              privacy_hidden_reason = COALESCE(p.privacy_hidden_reason, s.reason)
         FROM player_privacy_suppressions s
        WHERE (LOWER(p.grassroots_id) = s.grassroots_id OR LOWER(p.id::text) = s.grassroots_id)
          AND (p.privacy_hidden_at IS NULL OR p.is_public IS NOT FALSE)""",
]

DOWNGRADE: list[str] = [
    "DROP TRIGGER IF EXISTS player_privacy_enforce_upd ON players",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_ins ON players",
    "DROP FUNCTION IF EXISTS player_privacy_enforce()",
    "DROP TABLE IF EXISTS player_privacy_suppressions",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_reason",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_by",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_at",
]
