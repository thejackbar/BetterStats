"""Card review: which of a match's two stored versions the club shows, and its history.

A match can be stored twice: the synced Cricket Australia card (`games`) and the club's own
scorecard (`manual_games`: imported from a file, typed in, or read from a photo), linked by
`manual_games.superseded_by_game_id`. `pair_prefers_import` already says which one the site
shows. Card review adds three things on top of that and nothing underneath:

* ``review_choice``: what a person (or a bulk switch) chose, ``ca`` | ``club`` | ``hybrid``.
  NULL means nobody has chosen, so every existing match reads exactly as it did. ``hybrid`` is
  the club's card with Cricket Australia's detail copied onto it; it is displayed the same way
  as ``club`` (`pair_prefers_import` TRUE), the copied rows are what differ.
* ``review_source`` / ``review_decided_by`` / ``review_decided_at`` / ``review_note``: who and
  why. A choice made ``hand`` is never changed by a bulk switch.
* ``review_detail``: the opposition's card and dismissal text a ``hybrid`` choice copied.
* ``review_pair_ok``: a person looked at a pairing the scorecards do not confirm and said it
  is the same match, so it moves from "pairing looks wrong" to the normal review.

``card_review_log`` is the history, one row per change, with the state it replaced and the ids
of any rows a hybrid copy inserted, so one match can be put back exactly as it was.

ONE copy of the DDL: alembic's 351 and main.py's lifespan mirror both run STATEMENTS. Every
statement is idempotent.
"""

STATEMENTS = [
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_choice TEXT",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_source TEXT",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_decided_by UUID "
    "REFERENCES users(id) ON DELETE SET NULL",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_decided_at TIMESTAMPTZ",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_note TEXT",
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_pair_ok BOOLEAN NOT NULL DEFAULT FALSE",
    # What a ``hybrid`` choice copied that has no table of its own: the opposition's card and
    # the "c Sam Aplin b Wes Dagg" text for each dismissal. Kept apart from `extracted_payload`,
    # which means "read from a photo" to every reader of that column.
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS review_detail JSONB",
    """
    CREATE TABLE IF NOT EXISTS card_review_log (
        id SERIAL PRIMARY KEY,
        org_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        manual_game_id UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
        action TEXT NOT NULL,
        from_choice TEXT,
        to_choice TEXT,
        source TEXT NOT NULL DEFAULT 'hand',
        user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        note TEXT,
        batch_id UUID,
        before_state JSONB,
        detail JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        undone_at TIMESTAMPTZ
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_card_review_log_game ON card_review_log (manual_game_id, id)",
    "CREATE INDEX IF NOT EXISTS ix_card_review_log_batch ON card_review_log (batch_id) "
    "WHERE batch_id IS NOT NULL",
    "CREATE INDEX IF NOT EXISTS ix_card_review_log_org ON card_review_log (org_id, created_at DESC)",
]

# Downgrades drop what this added and never a table an earlier migration owns.
DOWNGRADE = [
    "DROP TABLE IF EXISTS card_review_log",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_detail",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_pair_ok",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_note",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_decided_at",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_decided_by",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_source",
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS review_choice",
]
