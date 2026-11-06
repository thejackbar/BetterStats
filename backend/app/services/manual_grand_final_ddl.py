"""The DDL behind "this hand-entered game was a grand final" (migration 373), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two copies cannot
drift. The lifespan re-runs the list on every boot, so every statement is idempotent.

``manual_games.is_grand_final``
    A person's own statement that a typed-in or imported match was the grand final. Cricket
    Australia names the round on a synced game (``games.round_name``); a hand-entered game has no
    round name, and ``is_final`` only says "some final", which a semi final is too. The automatic
    premierships (``services/premierships``) read this flag for a manual game, the way they read
    the round name for a synced one. NOT NULL, default FALSE: an existing game is not a grand
    final until somebody says so.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE manual_games ADD COLUMN IF NOT EXISTS is_grand_final BOOLEAN NOT NULL DEFAULT FALSE",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE manual_games DROP COLUMN IF EXISTS is_grand_final",
]
