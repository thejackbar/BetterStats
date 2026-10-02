"""The DDL behind the selection board's autosaved draft (migration 317), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the
two copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``selection_drafts``
    One row per fixture: the side a selector has been building but has not
    confirmed. ``fixture_lineups`` stays the CONFIRMED XI (votes, BetterIQ, the
    matchday board and the public Lineups page all read it), so a half-built
    side can never leak into them. ``draft`` is the board's own working state
    (slot positions including gaps, captain, keeper, pending call-up
    demotions); only ``routers/selection.py`` writes or reads it. Confirming
    the XI deletes the row. A draft is working state, not a record of what a
    player did, so it is not on ``merge_carry.CARRIED``.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS selection_drafts (
        fixture_id UUID PRIMARY KEY REFERENCES fixtures(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        draft JSONB NOT NULL DEFAULT '{}'::jsonb,
        updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS selection_drafts",
]
