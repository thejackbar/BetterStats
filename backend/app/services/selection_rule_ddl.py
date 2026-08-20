"""The DDL behind BetterSelect's association rules (migration 271), in ONE place.

Every schema change in this codebase is applied twice: once by alembic, and
once idempotently by ``main.py``'s lifespan so the API boots against a database
alembic hasn't reached yet. Those two copies are normally hand-kept in step,
which is exactly how they drift. This one is a single list both sides run, in
the same order, so they cannot. Every statement stays idempotent, because the
lifespan re-runs the whole list on every boot.

``selection_rules``
    One row per rule a club's association imposes — an age limit for a
    division, a cap on overseas players, qualifying games for finals. ``kind``
    picks the vocabulary; ``config`` holds that kind's own numbers; ``scope``
    says which fixtures it covers. See services/selection_rules.py, which is
    the only place either blob is written or read.

``selection_rule_players``
    A named exception to one rule for one player — a permit, an association
    clearance, or the tick a free-text rule asks for. Kept out of ``players``
    because it is per RULE: a fourteen year old cleared to play Division 1 is
    not thereby cleared of everything else.

``organisations.selection_rules_config``
    The club-wide defaults the rules lean on — chiefly how the association
    measures age (1 September, 1 January, or on the day), which is the setting
    that stops this being one association's rulebook.

``fixtures.is_final``
    NULL means "work it out from the round name", which is what every synced
    fixture does. Set explicitly when a club's association names its finals
    something the heuristic can't read.
"""

SELECTION_RULE_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS selection_rules (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        kind TEXT NOT NULL,
        name TEXT,
        enabled BOOLEAN NOT NULL DEFAULT true,
        severity TEXT NOT NULL DEFAULT 'warn',
        scope JSONB NOT NULL DEFAULT '{}'::jsonb,
        config JSONB NOT NULL DEFAULT '{}'::jsonb,
        position INTEGER NOT NULL DEFAULT 0,
        created_at TIMESTAMPTZ DEFAULT now(),
        updated_at TIMESTAMPTZ DEFAULT now()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_selection_rules_org "
    "ON selection_rules(organisation_id, position)",

    """
    CREATE TABLE IF NOT EXISTS selection_rule_players (
        rule_id UUID NOT NULL REFERENCES selection_rules(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        state TEXT NOT NULL DEFAULT 'cleared',
        note TEXT,
        updated_by UUID REFERENCES users(id) ON DELETE SET NULL,
        updated_at TIMESTAMPTZ DEFAULT now(),
        PRIMARY KEY (rule_id, player_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_selection_rule_players_org "
    "ON selection_rule_players(organisation_id, player_id)",

    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS selection_rules_config JSONB",

    # NULL = derive from the round name, which is what the fixture sync leaves
    # behind. A club whose association calls its finals something the heuristic
    # can't read sets it by hand on the fixture.
    "ALTER TABLE fixtures ADD COLUMN IF NOT EXISTS is_final BOOLEAN",
]
