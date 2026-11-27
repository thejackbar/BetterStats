"""The DDL behind a club leaving a whole match out of its players' stats (migration 401), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS`` (through ``superseded_ddl``, which owns the
views that read the table and so creates it first), so the copies cannot drift. Every statement is
idempotent, because the lifespan re-runs the list on every boot.

``game_stat_exclusions``
    One row per (club, match) the club chose to leave out of its players' figures: a friendly, a
    pre-season cup, a social T20 that sits in Cricket Australia's competition list. The match stays
    on Fixtures, Results and its scorecard. Only the club that made the choice loses it: a fixture
    between two clubs is one ``games`` row, and the other club's players keep their figures unless
    that club excludes it too.

    ``game_id`` has NO foreign key, as with ``game_exclusions`` and ``fow_overrides``: a Full Rebuild
    deletes every synced game and stores it again under the same id, which would cascade a foreign
    key and take the club's decision with it. ``source`` says which table the id lives in
    (``api`` for a synced game, ``manual`` for an uploaded or imported card).

    Counting it again never deletes the row (CLAUDE.md rule 7): ``restored_at`` and ``restored_by``
    are set and the row stays as the record of what was decided. Only a row with ``restored_at``
    NULL is in force, and the partial unique index keeps one in force per (club, match), so the
    match can be excluded, counted again and excluded again.

How the figures follow is in ``services/stat_exclusions.py``.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS game_stat_exclusions (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        source TEXT NOT NULL DEFAULT 'api',
        note TEXT,
        entered_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        restored_at TIMESTAMPTZ,
        restored_by UUID REFERENCES users(id) ON DELETE SET NULL
    )""",
    # One exclusion in force per club and match. A restored row steps out of the index, so the
    # history of a match excluded, counted again and excluded again is kept whole.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_game_stat_exclusions_live "
    "ON game_stat_exclusions (organisation_id, game_id) WHERE restored_at IS NULL",
    # What every effective view probes: tiny by construction, only the matches in force.
    "CREATE INDEX IF NOT EXISTS ix_game_stat_exclusions_game "
    "ON game_stat_exclusions (game_id) WHERE restored_at IS NULL",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS game_stat_exclusions",
]


def kept_sql(game_col: str, *player_cols: str) -> str:
    """SQL predicate: this per-game row is NOT left out of the figures by its player's club.

    A row is left out when the club that owns one of its players (``players.organisation_id``) has
    an exclusion in force on the row's match. Keyed through the player, never through the season
    that holds the game, because a game belongs to no club (CLAUDE.md rule 2): the other club's
    players on the same match keep their figures. A row with no player id (a fill-in, a redacted
    name) has no club to ask and is kept.

    ``game_col`` is the column holding the match id (``t.game_id``, ``t.manual_game_id``);
    ``player_cols`` the player id columns, any of which being one of the club's players takes the
    row out (a partnership where either batter is ours).
    """
    ids = ", ".join(player_cols)
    return ("NOT EXISTS (SELECT 1 FROM game_stat_exclusions _sx "
            "JOIN players _sxp ON _sxp.organisation_id = _sx.organisation_id "
            f"WHERE _sx.game_id = {game_col} AND _sx.restored_at IS NULL "
            f"AND _sxp.id IN ({ids}))")


def kept_for_org_sql(game_col: str, org_col: str) -> str:
    """SQL predicate: the club in ``org_col`` has no exclusion in force on the match in ``game_col``.

    For readers that already know whose figures they are adding up (the season view's scorecard
    branches, keyed by the club's own season or manual game)."""
    return ("NOT EXISTS (SELECT 1 FROM game_stat_exclusions _sxo "
            f"WHERE _sxo.game_id = {game_col} AND _sxo.organisation_id = {org_col} "
            "AND _sxo.restored_at IS NULL)")
