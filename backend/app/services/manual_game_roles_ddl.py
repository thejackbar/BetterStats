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

# Migration 382: ONE place that answers "who captained / kept wicket in this game", for a synced game
# (game_appearances) and a hand-entered one (manual_game_roles) alike. Every stats lens that filters on the
# captain or the keeper (Records, the Leaderboard filter, a player's captain record, StatLab) joins this view
# instead of game_appearances, which a hand-entered game never has a row in. Only the rows that carry a
# flag are in it, so a join to it is small; a game id here is the id the effective views give the game (a
# synced game's own id, a manual game's own id), so `bi.game_id = r.game_id` works for both.
VIEW_STATEMENTS: list[str] = [
    """
    CREATE OR REPLACE VIEW v_game_roles AS
        SELECT ga.game_id, ga.player_id, ga.is_captain, ga.is_wicket_keeper
        FROM game_appearances ga
        WHERE ga.is_captain OR ga.is_wicket_keeper
        UNION ALL
        SELECT r.manual_game_id AS game_id, r.player_id, r.is_captain, r.is_wicket_keeper
        FROM manual_game_roles r
        WHERE r.is_captain OR r.is_wicket_keeper
    """,
]

VIEW_DOWNGRADE: list[str] = [
    "DROP VIEW IF EXISTS v_game_roles",
]
