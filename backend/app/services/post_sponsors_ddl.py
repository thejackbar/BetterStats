"""DDL for the sponsors a club's posts start with (migration 320).

THE ONE COPY. Both alembic (versions/320_post_sponsor_defaults.py) and the
lifespan mirror in main.py run this same list. Every statement is idempotent,
because the lifespan re-runs the whole list on every boot.

One column: ``organisations.post_sponsor_defaults`` holds the sponsors a club
has pinned to a team or a grade, so every post for that team starts with them:
{"teams": {"1st xi": {"name": "1st XI", "sponsor_ids": ["<uuid>"]}},
 "grades": {"a grade": {"name": "A Grade", "sponsor_ids": []}}}.
Keys are the lower-cased, space-collapsed name; the name is kept for display.
NULL means no team has a sponsor of its own. Which sponsors a post gets is
DERIVED on read (services/post_sponsors.py), so a deleted sponsor or a changed
tier is never stale here.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS post_sponsor_defaults JSONB",
]

DOWNGRADE: list[str] = [
    "ALTER TABLE organisations DROP COLUMN IF EXISTS post_sponsor_defaults",
]
