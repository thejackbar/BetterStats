"""Sales Workspace — Phase 1 (core workspace + engagement panel).

Extends the existing CRM engine (migration 173) rather than forking a
parallel schema: the Sales Workspace is a new lens over the same
``crm_deals``/``crm_activities``/``crm_people`` rows the Sales Pipeline
board already manages. Two small additive columns:

- ``crm_activities.outcome`` — a structured call-outcome key (controlled
  vocabulary lives in ``services/sales_workspace.CALL_OUTCOMES``, not a DB
  enum — same posture as this codebase's other controlled vocabularies,
  e.g. ``services/scouting_intel.py``). NULL for every activity that isn't
  a logged call (notes/emails/system entries).
- ``crm_activities.next_follow_up_at`` — captured now so a later dedicated
  Follow-ups queue screen needs no backfill; Phase 1 only surfaces it
  inline on the workspace row/drawer.
- ``crm_people.directory_contact_id`` — traces a lazily-materialized
  ``crm_people`` row back to the ``marketing_club_contacts`` row it was
  created from (see ``services/sales_workspace.resolve_or_materialize_person``),
  and doubles as the dedupe key so a directory contact touched twice never
  mints two ``crm_people`` rows.

No new tables — reassignment history rides on the existing ``crm_activities``
timeline (a ``type='system'`` entry), and call-outcome disposition uses the
existing ``crm_deals.stage_id``/``status``/``lost_reason`` via the ordinary
``update_deal`` helper.

Revision ID: 255
Revises: 254
Create Date: 2026-08-15
"""
from alembic import op


revision = '255'
down_revision = '254'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS outcome TEXT")
    op.execute("ALTER TABLE crm_activities ADD COLUMN IF NOT EXISTS next_follow_up_at TIMESTAMPTZ")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_activities_follow_up "
        "ON crm_activities(next_follow_up_at) WHERE next_follow_up_at IS NOT NULL"
    )

    op.execute(
        "ALTER TABLE crm_people ADD COLUMN IF NOT EXISTS directory_contact_id "
        "UUID REFERENCES marketing_club_contacts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_crm_people_directory_contact "
        "ON crm_people(directory_contact_id) WHERE directory_contact_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_crm_people_directory_contact")
    op.execute("ALTER TABLE crm_people DROP COLUMN IF EXISTS directory_contact_id")
    op.execute("DROP INDEX IF EXISTS ix_crm_activities_follow_up")
    op.execute("ALTER TABLE crm_activities DROP COLUMN IF EXISTS next_follow_up_at")
    op.execute("ALTER TABLE crm_activities DROP COLUMN IF EXISTS outcome")
