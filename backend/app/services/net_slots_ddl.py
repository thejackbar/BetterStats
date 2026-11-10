"""The DDL behind time-slot nets (migration 385), in ONE place.

Alembic and ``main.py``'s lifespan both run ``STATEMENTS``, in order, so the two
copies cannot drift. The lifespan re-runs the list on every boot, so every
statement is idempotent.

``net_sessions.mode``
    ``manual`` (every existing session: one batting queue and a timer) or
    ``auto`` (a grid of nets by time slots, see ``services/net_slots.py``).

``net_sessions.slot_plan``
    The grid's plan: first time, slot length, finish time, second go, the nets
    and which squads feed each. NULL for a manual session.

``net_attendance.net_key`` / ``.slot_index`` / ``.slot_manual``
    Where a person sits on the grid: a net id from the plan, a slot number (0 =
    first slot), and whether somebody dragged them there (so a re-plan leaves
    them where they were put). Times are NOT stored: they are worked out from
    the plan, so changing the slot length corrects everything at once.

``uq_net_attendance_slot``
    One person per cell. Two phones checking in at the same moment cannot take
    the same slot; the loser is told and retries with fresh eyes.
"""

STATEMENTS: list[str] = [
    "ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'manual'",
    "ALTER TABLE net_sessions ADD COLUMN IF NOT EXISTS slot_plan JSONB",
    "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS net_key TEXT",
    "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS slot_index INTEGER",
    "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS slot_manual BOOLEAN NOT NULL DEFAULT false",
    "CREATE UNIQUE INDEX IF NOT EXISTS uq_net_attendance_slot "
    "ON net_attendance (session_id, net_key, slot_index) "
    "WHERE net_key IS NOT NULL AND slot_index IS NOT NULL",
]

DOWNGRADE: list[str] = [
    "DROP INDEX IF EXISTS uq_net_attendance_slot",
    "ALTER TABLE net_attendance DROP COLUMN IF EXISTS slot_manual",
    "ALTER TABLE net_attendance DROP COLUMN IF EXISTS slot_index",
    "ALTER TABLE net_attendance DROP COLUMN IF EXISTS net_key",
    "ALTER TABLE net_sessions DROP COLUMN IF EXISTS slot_plan",
    "ALTER TABLE net_sessions DROP COLUMN IF EXISTS mode",
]
