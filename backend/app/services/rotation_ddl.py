"""The DDL behind Junior Rotation (migration 381), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the
two copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

Junior Rotation is deliberately self-contained, because it is meant to outgrow
BetterSelect and become a product of its own. Its kids are TYPED NAMES saved
against the group (``rotation_players``), never rows in ``players``: a tee ball
side is often not on Cricket Australia at all, and nothing here may depend on a
club's synced roster. Nothing in it references ``players`` or ``grades``, so it
is not on ``merge_carry.CARRIED`` and a player merge cannot touch it.

``rotation_groups``
    One side that is rotated (an Under 8 tee ball team, a Kanga group). Holds
    its field positions (``positions``: ``[{id, name, key}]``, ``id`` stable so
    renaming a position does not orphan its history), how many field changes a
    game has (``innings``), how hard the generator leans on history
    (``fairness`` 0 to 100), and the parent link (``public_token``,
    ``public_enabled`` default OFF, ``public_show_surnames`` default OFF).
``rotation_players``
    The saved names. Never deleted: a kid who leaves gets ``former_at`` so their
    past rounds still read. ``avoid_positions`` is a list of position ids the
    generator keeps them out of while it can.
``rotation_rounds``
    One game or session. ``present`` is who is here, ``batting_order`` the
    batting order, ``fielding`` one ``{player_id: position_id | null}`` map per
    field change (null = resting). A DRAFT is working state; only a LOCKED round
    counts towards the history the next round is weighted by, so re-rolling a
    draft never changes what anyone has done. Tallies are derived on read.
    ``fixture_id`` optionally ties the round to a fixture (SET NULL, the round
    outlives a deleted fixture). ``version`` is bumped by every write.
"""

STATEMENTS: list[str] = [
    """CREATE TABLE IF NOT EXISTS rotation_groups (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        kind TEXT NOT NULL DEFAULT 'custom',
        positions JSONB NOT NULL DEFAULT '[]'::jsonb,
        innings INTEGER NOT NULL DEFAULT 1,
        fairness INTEGER NOT NULL DEFAULT 60,
        bats BOOLEAN NOT NULL DEFAULT TRUE,
        public_token TEXT,
        public_enabled BOOLEAN NOT NULL DEFAULT FALSE,
        public_show_surnames BOOLEAN NOT NULL DEFAULT FALSE,
        archived_at TIMESTAMPTZ,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_rotation_groups_org ON rotation_groups (organisation_id)",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_rotation_groups_token ON rotation_groups (public_token) WHERE public_token IS NOT NULL",
    """CREATE TABLE IF NOT EXISTS rotation_players (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        group_id UUID NOT NULL REFERENCES rotation_groups(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        avoid_positions JSONB NOT NULL DEFAULT '[]'::jsonb,
        note TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        former_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_rotation_players_group ON rotation_players (group_id)",
    """CREATE TABLE IF NOT EXISTS rotation_rounds (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        group_id UUID NOT NULL REFERENCES rotation_groups(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        round_date DATE NOT NULL,
        label TEXT,
        fixture_id UUID REFERENCES fixtures(id) ON DELETE SET NULL,
        status TEXT NOT NULL DEFAULT 'draft',
        present JSONB NOT NULL DEFAULT '[]'::jsonb,
        batting_order JSONB NOT NULL DEFAULT '[]'::jsonb,
        fielding JSONB NOT NULL DEFAULT '[]'::jsonb,
        warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
        version INTEGER NOT NULL DEFAULT 1,
        locked_at TIMESTAMPTZ,
        locked_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_rotation_rounds_group ON rotation_rounds (group_id, round_date)",
]

DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS rotation_rounds",
    "DROP TABLE IF EXISTS rotation_players",
    "DROP TABLE IF EXISTS rotation_groups",
]
