"""
DDL for automatic premierships (migration 365).

THE ONE COPY. Both alembic (versions/365_auto_premierships.py) and the lifespan
mirror in main.py run this same list, in this order. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

What is added, and why each piece is a column or table of its own:

  - ``games.round_name``: Cricket Australia's own round label ("Grand Final",
    "Semi Final", "Round 7"). ``games.is_final`` has only ever held "the round
    name contains 'final'", which is true of a semi final and a preliminary
    final as well, so a grand final cannot be told from it. Written by the
    sync beside ``is_final``; NULL until a game has been rediscovered.

  - ``player_achievements.linked_game_id``: the scorecard a Premiership honour
    belongs to. Set on a row the app wrote AND on a hand-typed row it could
    match to exactly one grand final, so the profile, the Premierships page
    and the scorecard all point at the same game. A link never changes what
    the row says.

  - ``player_achievements.auto_created``: TRUE only for a row the premiership
    reconcile wrote itself. It is the whole of "what this code may remove":
    a club's hand-typed honour is never deleted or edited by it, and a row a
    person edits is flipped to FALSE so it becomes theirs.

  - ``premiership_auto_exclusions``: a person who deletes an automatic honour
    has decided something, so the decision is kept (one row per club, game and
    player) and the reconcile never writes that honour again.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE games ADD COLUMN IF NOT EXISTS round_name TEXT",
    "ALTER TABLE player_achievements ADD COLUMN IF NOT EXISTS linked_game_id UUID",
    "ALTER TABLE player_achievements "
    "ADD COLUMN IF NOT EXISTS auto_created BOOLEAN NOT NULL DEFAULT FALSE",
    "CREATE INDEX IF NOT EXISTS ix_player_achievements_linked_game "
    "ON player_achievements(linked_game_id) WHERE linked_game_id IS NOT NULL",
    """
    CREATE TABLE IF NOT EXISTS premiership_auto_exclusions (
        org_id     UUID NOT NULL,
        game_id    UUID NOT NULL,
        player_id  UUID NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        PRIMARY KEY (org_id, game_id, player_id)
    )
    """,
]

# Never drops premiership_auto_exclusions' siblings or any column another
# migration owns; these three columns and the one table are ours alone.
DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS premiership_auto_exclusions",
    "DROP INDEX IF EXISTS ix_player_achievements_linked_game",
    "ALTER TABLE player_achievements DROP COLUMN IF EXISTS auto_created",
    "ALTER TABLE player_achievements DROP COLUMN IF EXISTS linked_game_id",
    "ALTER TABLE games DROP COLUMN IF EXISTS round_name",
]
