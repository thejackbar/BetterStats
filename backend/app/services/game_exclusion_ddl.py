"""The DDL behind a club marking a player as not having played a synced game (migration 391), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two copies cannot
drift. The lifespan re-runs the list on every boot, so every statement is idempotent.

``game_exclusions``
    One row per (club, game, player): the club says this player was named in the side but did not
    play (12th man, 13th man, a late withdrawal). The game stays on the team list with that reason
    and comes off every games-played count, because the row sets ``game_appearances.is_reserve``
    and every count already reads that flag (``game_status.appearance_counts_as_match``, the
    season view's reserve rule, the by-grade grid's ``uncounted`` map).

    ``game_id`` has NO foreign key, as with ``fow_overrides``: a Full Rebuild deletes every synced
    game and stores it again under the same id, which would cascade a foreign key and take the
    club's decision with it. The flag is written again each time sync stores the game
    (``game_exclusions.reapply``) and by the last statement below on every boot.
    ``prior_is_reserve`` is the flag as it stood before the club's mark, so taking the mark off
    puts the app's own judgement back. ``swapped_adjustment_id`` is the season adjustment the club
    moved onto this game (a -1 typed before this existed), so undoing the mark restores it.

    ``source`` is NULL for a mark made on the match page or the Adjustments screen, and ``premiers``
    for one written by giving the player 12th Man or 13th Man in the Premiers squad editor, so taking
    that role off takes the mark off and leaves a mark the club made by hand alone.

``game_sheet_checks``
    A side's team sheet with more than 11 names that the club has looked over (every such sheet named
    at least one extra, often a sub fielder in older seasons and finals). Kept so the list does not
    offer it again. ``team_name`` separates the two sides of a fixture between two of the club's teams.

``game_check_dismissals``
    A suggestion on the "Games to check" list the club looked at and kept as played. Kept so the
    list does not offer it again.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS game_exclusions (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        reason TEXT NOT NULL,
        note TEXT,
        prior_is_reserve BOOLEAN,
        swapped_adjustment_id INTEGER,
        source TEXT,
        entered_by UUID REFERENCES users(id) ON DELETE SET NULL,
        entered_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_game_exclusions UNIQUE (organisation_id, game_id, player_id)
    )""",
    "CREATE INDEX IF NOT EXISTS ix_game_exclusions_game ON game_exclusions (game_id)",
    "CREATE INDEX IF NOT EXISTS ix_game_exclusions_player ON game_exclusions (player_id)",
    """CREATE TABLE IF NOT EXISTS game_check_dismissals (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        dismissed_by UUID REFERENCES users(id) ON DELETE SET NULL,
        dismissed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_game_check_dismissals UNIQUE (organisation_id, game_id, player_id)
    )""",
    """CREATE TABLE IF NOT EXISTS game_sheet_checks (
        id SERIAL PRIMARY KEY,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        game_id UUID NOT NULL,
        team_name TEXT NOT NULL DEFAULT '',
        checked_by UUID REFERENCES users(id) ON DELETE SET NULL,
        checked_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_game_sheet_checks UNIQUE (organisation_id, game_id, team_name)
    )""",
    # Self-heal on every boot: a club's mark is written onto the appearance again wherever a sync,
    # a rebuild or a backfill script has put the flag back. Touches only rows that need it.
    """UPDATE game_appearances ga SET is_reserve = TRUE
         FROM game_exclusions e
        WHERE e.game_id = ga.game_id AND e.player_id = ga.player_id
          AND ga.is_reserve IS NOT TRUE""",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS game_sheet_checks",
    "DROP TABLE IF EXISTS game_check_dismissals",
    "DROP TABLE IF EXISTS game_exclusions",
]
