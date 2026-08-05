"""What running a live meeting needs that the schema did not have.

The committee tables already model a meeting well: agenda items carry a
``position``, motions already point at an agenda item, and an action can point
at a meeting and a motion (migration 217). Four things were missing, all of
them things a secretary does while the meeting is actually happening:

* an action raised under an agenda item had nowhere to record that,
* an action could only be given to ONE person, and "Dave and Priya will get
  the quotes" is the normal case, not the exception,
* motions had no order of their own, so they could not be arranged to follow
  the agenda they belong to,
* minutes are circulated but a secretary also keeps notes that are not, and
  there was only one field.

Revision ID: 220
Revises: 219
"""
from alembic import op

revision = "220"
down_revision = "219"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # An action raised while discussing an agenda item remembers which one.
    op.execute("""
        ALTER TABLE committee_tasks
        ADD COLUMN IF NOT EXISTS agenda_item_id UUID
        REFERENCES meeting_agenda_items(id) ON DELETE SET NULL
    """)

    # Several people can own one action. `assigned_to_member_id` stays as the
    # primary owner so every existing reader keeps working untouched; this
    # table holds the full set, seeded from that column below.
    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_task_assignees (
            task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, member_id)
        )
    """)
    op.execute("""
        INSERT INTO committee_task_assignees (task_id, member_id)
        SELECT id, assigned_to_member_id FROM committee_tasks
        WHERE assigned_to_member_id IS NOT NULL
        ON CONFLICT DO NOTHING
    """)

    # Motions get their own order so they can sit against the agenda.
    op.execute("ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0")

    # Minutes are the record that gets circulated. These are the secretary's
    # own notes and are never part of it.
    op.execute("ALTER TABLE committee_meetings ADD COLUMN IF NOT EXISTS private_notes TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE committee_meetings DROP COLUMN IF EXISTS private_notes")
    op.execute("ALTER TABLE meeting_motions DROP COLUMN IF EXISTS position")
    op.execute("DROP TABLE IF EXISTS committee_task_assignees")
    op.execute("ALTER TABLE committee_tasks DROP COLUMN IF EXISTS agenda_item_id")
