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
    # An admin said "this is a different person": the name match stops for this row.
    "ALTER TABLE players ADD COLUMN IF NOT EXISTS privacy_name_cleared_at TIMESTAMPTZ",
    """CREATE TABLE IF NOT EXISTS player_privacy_suppressions (
        grassroots_id TEXT PRIMARY KEY,
        reason TEXT,
        created_by TEXT,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "ALTER TABLE player_privacy_suppressions ADD COLUMN IF NOT EXISTS names TEXT[]",
    # The canonical name key. Splits on anything that is not a letter or digit,
    # lower-cases, sorts the words, joins them. NULL for an empty name. One copy,
    # in SQL, so the trigger and the Python that records a person's names agree.
    r"""CREATE OR REPLACE FUNCTION privacy_name_key(txt TEXT) RETURNS TEXT AS $fn$
        SELECT NULLIF(string_agg(w, ' ' ORDER BY w), '')
          FROM unnest(regexp_split_to_array(lower(COALESCE(txt, '')), '[\W_]+')) AS w
         WHERE w <> ''
    $fn$ LANGUAGE sql IMMUTABLE""",
    # Suppressions recorded before names were kept: take them from the person's
    # own hidden rows. Runs once per suppression (names IS NULL), then never.
    """UPDATE player_privacy_suppressions s
          SET names = COALESCE((
                SELECT array_agg(DISTINCT q.k)
                  FROM (
                    SELECT privacy_name_key(p.name) AS k
                      FROM players p
                     WHERE p.privacy_hidden_at IS NOT NULL
                       AND p.privacy_hidden_by IS DISTINCT FROM 'name-match'
                       AND (LOWER(p.grassroots_id) = s.grassroots_id OR LOWER(p.id::text) = s.grassroots_id)
                    UNION
                    SELECT privacy_name_key(to_jsonb(p) ->> 'display_name_override')
                      FROM players p
                     WHERE p.privacy_hidden_at IS NOT NULL
                       AND p.privacy_hidden_by IS DISTINCT FROM 'name-match'
                       AND (LOWER(p.grassroots_id) = s.grassroots_id OR LOWER(p.id::text) = s.grassroots_id)
                  ) q
                 WHERE q.k IS NOT NULL AND array_length(string_to_array(q.k, ' '), 1) >= 2
                   AND NOT EXISTS (SELECT 1 FROM unnest(string_to_array(q.k, ' ')) w WHERE length(w) < 2)
              ), CAST('{}' AS TEXT[]))
        WHERE s.names IS NULL""",
    # to_jsonb(NEW) reads grassroots_id and display_name_override without naming
    # the columns, so the same function loads on a database whose players table
    # lacks one.
    r"""CREATE OR REPLACE FUNCTION player_privacy_enforce() RETURNS trigger AS $fn$
    DECLARE
        sup RECORD;
        gid TEXT;
        nk TEXT;
        dk TEXT;
    BEGIN
        gid := NULLIF(to_jsonb(NEW) ->> 'grassroots_id', '');
        SELECT s.reason, s.created_by INTO sup
          FROM player_privacy_suppressions s
         WHERE s.grassroots_id IN (LOWER(COALESCE(gid, '')), LOWER(NEW.id::text))
         LIMIT 1;
        IF FOUND THEN
            NEW.is_public := FALSE;
            IF NEW.privacy_hidden_at IS NULL THEN
                NEW.privacy_hidden_at := NOW();
                NEW.privacy_hidden_by := COALESCE(sup.created_by, 'suppression');
                NEW.privacy_hidden_reason := sup.reason;
            END IF;
            RETURN NEW;
        END IF;

        -- No participant id (hand-typed, imported): match on the full name.
        IF gid IS NULL AND NEW.privacy_name_cleared_at IS NULL THEN
            nk := privacy_name_key(NEW.name);
            dk := privacy_name_key(to_jsonb(NEW) ->> 'display_name_override');
            PERFORM 1 FROM player_privacy_suppressions s
             WHERE (nk IS NOT NULL AND nk = ANY(s.names))
                OR (dk IS NOT NULL AND dk = ANY(s.names))
             LIMIT 1;
            IF FOUND THEN
                NEW.is_public := FALSE;
                IF NEW.privacy_hidden_at IS NULL THEN
                    NEW.privacy_hidden_at := NOW();
                    NEW.privacy_hidden_by := 'name-match';
                    NEW.privacy_hidden_reason := 'The name matches a person who asked to be removed from the public website. Held until an admin confirms this is a different person.';
                END IF;
                RETURN NEW;
            END IF;
        END IF;

        -- Held by name earlier, and no longer matches (renamed, or the person was
        -- put back): let it go. Only a hold WE placed is ever lifted here.
        IF NEW.privacy_hidden_by = 'name-match' THEN
            NEW.privacy_hidden_at := NULL;
            NEW.privacy_hidden_by := NULL;
            NEW.privacy_hidden_reason := NULL;
            NEW.is_public := TRUE;
        END IF;
        RETURN NEW;
    END
    $fn$ LANGUAGE plpgsql""",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_ins ON players",
    """CREATE TRIGGER player_privacy_enforce_ins BEFORE INSERT ON players
       FOR EACH ROW EXECUTE PROCEDURE player_privacy_enforce()""",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_upd ON players",
    """CREATE TRIGGER player_privacy_enforce_upd
       BEFORE UPDATE OF is_public, privacy_hidden_at, grassroots_id, name, display_name_override,
                        privacy_name_cleared_at ON players
       FOR EACH ROW EXECUTE PROCEDURE player_privacy_enforce()""",
    # Rows that predate the trigger. Match nothing once they are all marked.
    """UPDATE players p
          SET is_public = FALSE,
              privacy_hidden_at = COALESCE(p.privacy_hidden_at, NOW()),
              privacy_hidden_by = COALESCE(p.privacy_hidden_by, s.created_by, 'suppression'),
              privacy_hidden_reason = COALESCE(p.privacy_hidden_reason, s.reason)
         FROM player_privacy_suppressions s
        WHERE (LOWER(p.grassroots_id) = s.grassroots_id OR LOWER(p.id::text) = s.grassroots_id)
          AND (p.privacy_hidden_at IS NULL OR p.is_public IS NOT FALSE)""",
    # Hand-typed rows whose name is on a suppression. SET name = name runs the
    # UPDATE trigger, which does the matching; a no-op once they are marked.
    """UPDATE players p SET name = p.name
        WHERE NULLIF(p.grassroots_id, '') IS NULL
          AND p.privacy_name_cleared_at IS NULL
          AND p.privacy_hidden_at IS NULL
          AND EXISTS (SELECT 1 FROM player_privacy_suppressions s
                       WHERE s.names IS NOT NULL
                         AND (privacy_name_key(p.name) = ANY(s.names)
                              OR privacy_name_key(to_jsonb(p) ->> 'display_name_override') = ANY(s.names)))""",
]

DOWNGRADE: list[str] = [
    "DROP TRIGGER IF EXISTS player_privacy_enforce_upd ON players",
    "DROP TRIGGER IF EXISTS player_privacy_enforce_ins ON players",
    "DROP FUNCTION IF EXISTS player_privacy_enforce()",
    "DROP FUNCTION IF EXISTS privacy_name_key(TEXT)",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_name_cleared_at",
    "DROP TABLE IF EXISTS player_privacy_suppressions",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_reason",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_by",
    "ALTER TABLE players DROP COLUMN IF EXISTS privacy_hidden_at",
]
