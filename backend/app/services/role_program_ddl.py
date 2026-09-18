"""The ONE copy of the Role Program handover DDL.

Alembic (migration 306) and `main.py`'s lifespan mirror both run this list, in
this order, per the `vote_medal_ddl` rule — two copies is how the two drift.
Every statement is idempotent, because the lifespan re-runs the whole list on
every boot.

WHAT THIS IS FOR. A club's Role Program (what a role entails — its purpose, its
recurring/seasonal/matchday duties, the operational areas it covers) is
assembled on READ from the role, its Club Diary tasks and its roster areas — it
needs no storage of its own. The MEASURABLE half is succession: when a role
changes hands, a responsible person works an onboarding checklist and records,
per element, whether the new volunteer has been walked through it and has
understood and accepted it. That checklist is these two tables.

WHY THE ITEMS ARE A SNAPSHOT, NOT A LIVE JOIN. Each item copies its element's
label / detail / cadence at the moment the handover is started (the snapshot
discipline `committee_terms.holder_name` and `volunteer_hours.is_paid` already
keep), so editing or archiving a Diary task months later can never rewrite what
a past onboarding recorded. `source_definition_id` is a SET-NULL link back to
the live task for convenience only; `source_key` is what a reseed dedupes on, so
a handover started before a duty existed can pull it in without ever
double-adding one it already holds.
"""

STATEMENTS: list[str] = [
    # One handover = one person being onboarded into one role (or one role
    # changing hands). Keyed on club_roles, which is the ONE anchor for both a
    # volunteer role and a committee seat (a committee position IS a
    # committee-flagged club_role). role_title is snapshotted so an archived or
    # renamed role never blanks a past handover; role_id SET NULL keeps the
    # handover after the role itself is gone.
    """
    CREATE TABLE IF NOT EXISTS role_program_handovers (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        role_id UUID REFERENCES club_roles(id) ON DELETE SET NULL,
        role_title TEXT NOT NULL,
        committee_position_id UUID REFERENCES committee_positions(id) ON DELETE SET NULL,
        incoming_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
        incoming_name TEXT,
        outgoing_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
        outgoing_name TEXT,
        status TEXT NOT NULL DEFAULT 'in_progress',
        started_on DATE NOT NULL DEFAULT CURRENT_DATE,
        target_date DATE,
        completed_at TIMESTAMPTZ,
        notes TEXT,
        created_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    # One checklist line. source_kind says what kind of element it is
    # (responsibility / duty / area / knowledge / custom); source_key is the
    # source row's id (or a synthetic like 'position:responsibilities') and is
    # what a reseed dedupes on. A custom item — a piece of tribal knowledge the
    # responsible person types in ("where the shed key lives") — carries a NULL
    # source_key, so the dedupe index below never fires for it.
    """
    CREATE TABLE IF NOT EXISTS role_program_handover_items (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        handover_id UUID NOT NULL REFERENCES role_program_handovers(id) ON DELETE CASCADE,
        source_kind TEXT NOT NULL,
        source_key TEXT,
        source_definition_id UUID REFERENCES club_diary_task_definitions(id) ON DELETE SET NULL,
        label TEXT NOT NULL,
        detail TEXT,
        cadence TEXT,
        status TEXT NOT NULL DEFAULT 'pending',
        target_date DATE,
        note TEXT,
        sort_order INTEGER NOT NULL DEFAULT 0,
        updated_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_role_program_handovers_org_role "
    "ON role_program_handovers (organisation_id, role_id)",
    "CREATE INDEX IF NOT EXISTS ix_role_program_handover_items_handover "
    "ON role_program_handover_items (handover_id)",
    # A reseed must never add an element the handover already holds. A custom
    # item has no source and is exempt (partial index), so a club can add two
    # knowledge notes with the same words if it wants to.
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_role_program_handover_item_src "
    "ON role_program_handover_items (handover_id, source_kind, source_key) "
    "WHERE source_key IS NOT NULL",
]
