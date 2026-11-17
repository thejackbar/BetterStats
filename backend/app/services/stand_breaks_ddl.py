"""The DDL behind unbroken and retired partnerships, club match tags and linked partnership records
(migration 389), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two copies cannot
drift. The lifespan re-runs the list on every boot, so every statement is idempotent.

``COLUMN_STATEMENTS`` must run BEFORE anything re-issues ``v_effective_partnerships``: the view
selects ``is_unbroken`` from both tables, and the lifespan re-issues the view early (and again in
``services/superseded_ddl``). ``main.py`` runs them right before its first copy of the view.

``fow_override_breaks``
    What a club typed about an innings of a synced match that is not a wicket: a batter who
    retired (``kind = 'retired'``) and the stand still going when the innings ended
    (``kind = 'unbroken'``). Read with ``fow_overrides`` and turned into partnerships by
    ``services/stand_breaks``. ``after_wicket`` is how many wickets had fallen when it
    happened. Like ``fow_overrides``, ``game_id`` has NO foreign key, so a Full Rebuild keeps it.

``partnerships.is_unbroken`` / ``manual_partnerships.is_unbroken``
    TRUE for a stand no wicket ended (a retirement or the end of the innings). NULL means the
    source does not say, which is every row written before this.

``manual_partnership_records.linked_game_id``
    The match a hand-typed record was made in, so the records board can open its scorecard.
    A synced or a manual game id, so no foreign key (a Full Rebuild re-stores synced games).

``club_match_tags``
    What a club says a match was, for its premierships: ``normal`` (not a final, whatever the round
    name says), ``final`` (a final, not the decider) or ``grand_final``. ``won`` is the club's own word
    that it won, for a grand final with no winner on the card (washed out and won on the ladder).
    Entered from the admin Premierships screen by pasting a play.cricket.com.au match link or ID, or
    from the match page's Premiers tick (``grand_final`` + ``won``). ``services/premierships`` reads it
    before the round name. Per club, since a game belongs to no club; no foreign key to the game, so
    a Full Rebuild keeps it.
"""

COLUMN_STATEMENTS: list[str] = [
    "ALTER TABLE partnerships ADD COLUMN IF NOT EXISTS is_unbroken BOOLEAN",
    "ALTER TABLE manual_partnerships ADD COLUMN IF NOT EXISTS is_unbroken BOOLEAN",
]

STATEMENTS: list[str] = COLUMN_STATEMENTS + [
    """CREATE TABLE IF NOT EXISTS fow_override_breaks (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        innings_number INTEGER NOT NULL,
        kind TEXT NOT NULL,
        after_wicket INTEGER NOT NULL DEFAULT 0,
        score INTEGER,
        participant_id TEXT,
        batter_name TEXT,
        entered_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_fow_override_breaks_game ON fow_override_breaks (organisation_id, game_id)",
    "ALTER TABLE manual_partnership_records ADD COLUMN IF NOT EXISTS linked_game_id UUID",
    """CREATE TABLE IF NOT EXISTS club_match_tags (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        kind TEXT NOT NULL,
        won BOOLEAN NOT NULL DEFAULT FALSE,
        tagged_by UUID REFERENCES users(id) ON DELETE SET NULL,
        tagged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_club_match_tags UNIQUE (organisation_id, game_id),
        CONSTRAINT ck_club_match_tags_kind CHECK (kind IN ('normal', 'final', 'grand_final'))
    )""",
]

# The view reads is_unbroken, so the downgrade puts back the view without it first
# (DROP and re-create: CREATE OR REPLACE cannot remove a column), then drops what 389 added.
DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS club_match_tags",
    "ALTER TABLE manual_partnership_records DROP COLUMN IF EXISTS linked_game_id",
    "DROP TABLE IF EXISTS fow_override_breaks",
]
