"""The ONE copy of the BetterComms Lists→Segments merge DDL.

Alembic (migration 304) and `main.py`'s lifespan mirror both run this list, in
this order, per the `vote_medal_ddl` rule — two copies is how the two drift.
Every statement is idempotent, because the lifespan re-runs the whole list on
every boot.

WHY THIS EXISTS. "Lists" and "Segments" were two audience concepts a user had
to learn separately: a Segment is a live RULE, a List is a hand-picked ROLL
CALL. They are folded into one — a Segment now also carries a frozen,
hand-picked STATIC member set (`comms_segment_members`), and the final audience
is the UNION of (rule matches) ∪ (the static set). Every existing list becomes
a pure-static segment.

WHY A NEW MEMBER TABLE RATHER THAN A JSONB ARRAY. A club can have 1500+
contacts, and add/remove-a-member must not rewrite a blob — the same reason
`comms_list_members` was a table. `comms_lists` / `comms_list_members` are KEPT
(history + `saved_list` campaign back-compat); nothing writes them after this.

`legacy_list_id` maps a migrated segment back to the list it came from, which is
what makes the backfill idempotent and lets `_resolve_audience` resolve a
historical `saved_list` campaign against the migrated segment.
"""

STATEMENTS: list[str] = [
    # A segment now carries the same grouping a list did — `source` ('manual' |
    # 'auto') and an `origin` label — so an auto-generated segment (CRM Sales
    # Pipeline, Wizard Clubs, Club Admin Users) reads and manages the same as a
    # hand-built one in the unified Segments screen.
    "ALTER TABLE comms_segments ADD COLUMN IF NOT EXISTS source TEXT NOT NULL DEFAULT 'manual'",
    "ALTER TABLE comms_segments ADD COLUMN IF NOT EXISTS origin TEXT",
    "ALTER TABLE comms_segments ADD COLUMN IF NOT EXISTS legacy_list_id UUID",
    # One segment per migrated list. Partial-unique so an unmigrated segment
    # carries NULL freely while a migrated one is unique on the list it came
    # from — which is also what makes the backfill's NOT EXISTS guard exact.
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_comms_segments_legacy_list
        ON comms_segments(legacy_list_id) WHERE legacy_list_id IS NOT NULL
    """,
    # The frozen hand-picked set. Mirror of comms_list_members: cascaded to both
    # the segment and the contact, so a deleted contact drops out automatically.
    """
    CREATE TABLE IF NOT EXISTS comms_segment_members (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        segment_id UUID NOT NULL REFERENCES comms_segments(id) ON DELETE CASCADE,
        contact_id UUID NOT NULL REFERENCES comms_contacts(id) ON DELETE CASCADE,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        CONSTRAINT uq_comms_segment_member UNIQUE (segment_id, contact_id)
    )
    """,
    "CREATE INDEX IF NOT EXISTS ix_comms_segment_members_segment ON comms_segment_members(segment_id)",
    # The Wizard-Clubs export ledger keyed on the list it created (migration
    # 251, `list_id` has no FK). It now records the SEGMENT it created instead;
    # `list_id` is kept for the exports made before this. `_exports_by_key`
    # joins whichever is set to resolve the container's current name.
    "ALTER TABLE wizard_club_lists ADD COLUMN IF NOT EXISTS segment_id UUID",
    "ALTER TABLE wizard_club_lists ALTER COLUMN list_id DROP NOT NULL",
    """
    CREATE UNIQUE INDEX IF NOT EXISTS uq_wizard_club_lists_segment_club
        ON wizard_club_lists(segment_id, club_key) WHERE segment_id IS NOT NULL
    """,
    # ── Backfill: every existing list becomes a pure-static segment ───────────
    # Guarded on the legacy link so a re-run (every boot) is a no-op. The CASE
    # suffixes the name only when a NON-migrated segment already owns
    # (org, name) — both `comms_lists.name` and `comms_segments.name` are unique
    # per org, so a list name can only ever collide with a hand-built segment,
    # never with another list.
    """
    INSERT INTO comms_segments (id, organisation_id, name, definition, source, origin,
                                legacy_list_id, created_at, updated_at)
    SELECT gen_random_uuid(), l.organisation_id,
           CASE WHEN EXISTS (SELECT 1 FROM comms_segments s2
                              WHERE s2.organisation_id = l.organisation_id
                                AND s2.name = l.name
                                AND s2.legacy_list_id IS DISTINCT FROM l.id)
                THEN l.name || ' (list ' || substr(l.id::text, 1, 8) || ')'
                ELSE l.name END,
           '{"match": "all", "rules": []}'::jsonb,
           COALESCE(l.source, 'manual'), l.origin, l.id, l.created_at, NOW()
    FROM comms_lists l
    WHERE NOT EXISTS (SELECT 1 FROM comms_segments s WHERE s.legacy_list_id = l.id)
    """,
    # Carry each list's members onto its migrated segment.
    """
    INSERT INTO comms_segment_members (id, segment_id, contact_id, created_at)
    SELECT gen_random_uuid(), s.id, lm.contact_id, lm.created_at
    FROM comms_list_members lm
    JOIN comms_segments s ON s.legacy_list_id = lm.list_id
    ON CONFLICT (segment_id, contact_id) DO NOTHING
    """,
    # Point the Wizard-Clubs ledger's historical rows at the segments their
    # lists became, so its export report resolves the container name off the
    # segment going forward. Guarded so a re-run writes nothing.
    """
    UPDATE wizard_club_lists w
    SET segment_id = s.id
    FROM comms_segments s
    WHERE s.legacy_list_id = w.list_id AND w.list_id IS NOT NULL AND w.segment_id IS NULL
    """,
]
