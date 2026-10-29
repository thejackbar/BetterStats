"""The DDL behind "who captained and who kept wicket in a hand-entered game" (migration 377), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two copies cannot drift. The
lifespan re-runs the list on every boot, so every statement is idempotent.

``manual_game_roles``
    One row for each player who was the captain or the wicket keeper of a manual (typed-in or imported)
    game, with the two flags. A player who held neither has no row, so the table is exactly "the
    people the club named". It is a table of its own, not columns on the batting rows, because a
    captain who did not bat has no batting row, and because the same person is on one row per innings
    there. A synced game keeps these on ``game_appearances``; a hand-entered game has no such table.

    Two keepers in one match is real (a keeper replaced mid-match), so a game can have more than one
    row flagged; the screens show one and keep the rest. ``player_id`` is ``ON DELETE CASCADE`` like
    every manual per-game table, which is why ``services/merge_carry.CARRIED`` lists it: a merge moves
    the role to the kept player rather than letting the delete take it.

    No ``created_at``: a snapshot of the rows (for undo) is JSON, and a timestamp does not round-trip.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS manual_game_roles (
        id               SERIAL PRIMARY KEY,
        manual_game_id   UUID NOT NULL REFERENCES manual_games(id) ON DELETE CASCADE,
        player_id        UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        is_captain       BOOLEAN NOT NULL DEFAULT FALSE,
        is_wicket_keeper BOOLEAN NOT NULL DEFAULT FALSE,
        UNIQUE (manual_game_id, player_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_manual_game_roles_player ON manual_game_roles (player_id)",
]

# Drops only the table this migration added.
DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS manual_game_roles",
]
