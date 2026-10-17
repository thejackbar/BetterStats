"""The DDL behind the player dashboard and Fines (migration 341), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``organisations.player_dashboard_modules``
    The ordered list of module keys a club shows on a player's own page (the
    "My page" tab of the self-service link). NULL means the club never chose,
    which reads as the page every club had before: availability, squad,
    selected, training (plus fines, which only shows for a squad that turned it
    on).

Fines (BetterSelect). A balance is derived on read from the two ledgers, never
stored; nothing here is ever deleted, a wrong row is voided (``voided_at``) so
the trail stays.

``fine_settings``  one row per squad: on/off and how to pay into the pot.
``fine_types``     the squad's quick-pick list (name + default amount), archived
                   rather than deleted.
``fine_entries``   one row per fine handed out, on a date.
``fine_payments``  money a player tipped into the pot, recorded by an admin.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS player_dashboard_modules JSONB",
    """CREATE TABLE IF NOT EXISTS fine_settings (
        team_id UUID PRIMARY KEY REFERENCES teams(id) ON DELETE CASCADE,
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        enabled BOOLEAN NOT NULL DEFAULT FALSE,
        payid TEXT,
        payid_name TEXT,
        account_name TEXT,
        bsb TEXT,
        account_number TEXT,
        reference_hint TEXT,
        other_instructions TEXT,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    """CREATE TABLE IF NOT EXISTS fine_types (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        amount NUMERIC(10,2) NOT NULL DEFAULT 0,
        sequence INTEGER NOT NULL DEFAULT 0,
        archived_at TIMESTAMPTZ,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )""",
    "CREATE INDEX IF NOT EXISTS ix_fine_types_team ON fine_types (team_id)",
    """CREATE TABLE IF NOT EXISTS fine_entries (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        fine_type_id UUID REFERENCES fine_types(id) ON DELETE SET NULL,
        reason TEXT NOT NULL,
        amount NUMERIC(10,2) NOT NULL,
        fined_on DATE NOT NULL,
        created_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        voided_at TIMESTAMPTZ,
        voided_by UUID REFERENCES users(id) ON DELETE SET NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_fine_entries_team_player ON fine_entries (team_id, player_id)",
    "CREATE INDEX IF NOT EXISTS ix_fine_entries_player ON fine_entries (player_id)",
    """CREATE TABLE IF NOT EXISTS fine_payments (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        team_id UUID NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
        player_id UUID NOT NULL REFERENCES players(id) ON DELETE CASCADE,
        amount NUMERIC(10,2) NOT NULL,
        paid_on DATE NOT NULL,
        method TEXT,
        note TEXT,
        recorded_by UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        voided_at TIMESTAMPTZ,
        voided_by UUID REFERENCES users(id) ON DELETE SET NULL
    )""",
    "CREATE INDEX IF NOT EXISTS ix_fine_payments_team_player ON fine_payments (team_id, player_id)",
    "CREATE INDEX IF NOT EXISTS ix_fine_payments_player ON fine_payments (player_id)",
]

# Drops only what this migration added. Never a table an earlier migration owns.
DOWNGRADE: list[str] = [
    "DROP TABLE IF EXISTS fine_payments",
    "DROP TABLE IF EXISTS fine_entries",
    "DROP TABLE IF EXISTS fine_types",
    "DROP TABLE IF EXISTS fine_settings",
    "ALTER TABLE organisations DROP COLUMN IF EXISTS player_dashboard_modules",
]
