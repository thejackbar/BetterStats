"""DDL for hiding a club's junior programme from its public Stats (migration 315).

THE ONE COPY. Both alembic (versions/315_hide_juniors.py) and the lifespan
mirror in main.py run this same list, in this order. Every statement is
idempotent, because the lifespan re-runs the whole list on every boot.

Two columns and nothing else, on purpose. Which players are hidden, and which
games count as junior, are DERIVED on read (services/junior_hiding.py) from a
club's own competition tags and its games. A stored "is a hidden junior" flag
would be wrong the moment a game is corrected, a competition is re-tagged or
sync lands a senior fixture.

  - ``club_competitions.is_junior`` is tri-state. NULL means nobody has said,
    and the reader falls back to a guess from the competition's name (the same
    "suggestion on read, nothing written as a guess" rule grade categories
    follow). TRUE / FALSE is a person's decision and is never overwritten by
    sync or by a re-seed.
  - ``organisations.hide_juniors`` is the club's switch. Off for everybody, so
    no established club's public pages change because of an upgrade.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE club_competitions ADD COLUMN IF NOT EXISTS is_junior BOOLEAN",
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS hide_juniors BOOLEAN NOT NULL DEFAULT false",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS hide_juniors",
    "ALTER TABLE club_competitions DROP COLUMN IF EXISTS is_junior",
]
