"""Committee governance: resolutions, per-member votes, action budgets,
dependencies, objectives and threaded notes.

The committee could already record a meeting, its agenda, its motions and the
actions that came out of them. What it could not do was the governance around
them: say that a passed motion became a resolution, record who actually voted
which way (only tallies were stored), give an action a budget and a percentage
complete, make one action wait on another, hang the whole lot off a strategic
objective, or leave a note on any of it.

Everything here is additive. Existing motions keep their tallies, existing
tasks keep working with the new columns null.

Revision ID: 217
Revises: 216
"""
from alembic import op

revision = "217"
down_revision = "216"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── The business plan an action can serve ────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS club_objectives (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            description TEXT,
            -- The plan this objective belongs to, free text so a club can run
            -- "Strategic Plan 2026-29" and "Facilities Plan" side by side.
            plan TEXT,
            season_year INTEGER,
            status TEXT NOT NULL DEFAULT 'active',
            sort_order INTEGER NOT NULL DEFAULT 0,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_club_objectives_org ON club_objectives(organisation_id, status)")

    # ── Actions become plannable ─────────────────────────────────────────────
    for col, ddl in [
        ("objective_id", "UUID REFERENCES club_objectives(id) ON DELETE SET NULL"),
        ("budget_estimate", "NUMERIC(12,2)"),
        ("actual_expenditure", "NUMERIC(12,2)"),
        ("percent_complete", "INTEGER NOT NULL DEFAULT 0"),
        ("start_date", "DATE"),
        ("closed_by_member_id", "UUID REFERENCES fee_members(id) ON DELETE SET NULL"),
        ("outcome_notes", "TEXT"),
        # Where an action came from, so "this was resolved at the March meeting"
        # survives even after the meeting scrolls out of view.
        ("meeting_id", "UUID REFERENCES committee_meetings(id) ON DELETE SET NULL"),
        ("motion_id", "UUID REFERENCES meeting_motions(id) ON DELETE SET NULL"),
    ]:
        op.execute(f"ALTER TABLE committee_tasks ADD COLUMN IF NOT EXISTS {col} {ddl}")

    # An action can wait on other actions. Same shape as diary_task_dependencies.
    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_task_dependencies (
            task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
            depends_on_task_id UUID NOT NULL REFERENCES committee_tasks(id) ON DELETE CASCADE,
            PRIMARY KEY (task_id, depends_on_task_id)
        )
    """)

    # ── A passed motion can become a resolution ──────────────────────────────
    for col, ddl in [
        ("is_resolution", "BOOLEAN NOT NULL DEFAULT FALSE"),
        # The club's own reference, e.g. "R2026-04". Free text: numbering
        # conventions differ and nobody wants ours imposed on them.
        ("resolution_ref", "TEXT"),
        ("resolved_at", "TIMESTAMPTZ"),
    ]:
        op.execute(f"ALTER TABLE meeting_motions ADD COLUMN IF NOT EXISTS {col} {ddl}")

    # Who voted which way. The tallies on meeting_motions stay as the summary —
    # a club that just counts hands in the room still only has a count, and a
    # club that records names gets both.
    op.execute("""
        CREATE TABLE IF NOT EXISTS meeting_motion_votes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            motion_id UUID NOT NULL REFERENCES meeting_motions(id) ON DELETE CASCADE,
            member_id UUID NOT NULL REFERENCES fee_members(id) ON DELETE CASCADE,
            vote TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_motion_vote_per_member UNIQUE (motion_id, member_id)
        )
    """)

    # ── Notes and documents against anything ─────────────────────────────────
    op.execute("""
        CREATE TABLE IF NOT EXISTS committee_notes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            entity_type TEXT NOT NULL,
            entity_id UUID NOT NULL,
            body TEXT NOT NULL,
            author_member_id UUID REFERENCES fee_members(id) ON DELETE SET NULL,
            author_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_notes_entity ON committee_notes(organisation_id, entity_type, entity_id)")

    # The document registry stays link-based (governance docs live where the
    # club already keeps them). It just learns what a document is attached to,
    # so a quote requested by the committee hangs off that action.
    op.execute("ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS entity_type TEXT")
    op.execute("ALTER TABLE committee_documents ADD COLUMN IF NOT EXISTS entity_id UUID")
    op.execute("CREATE INDEX IF NOT EXISTS ix_committee_documents_entity ON committee_documents(organisation_id, entity_type, entity_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meeting_motion_votes")
    op.execute("DROP TABLE IF EXISTS committee_task_dependencies")
    op.execute("DROP TABLE IF EXISTS committee_notes")
    op.execute("DROP INDEX IF EXISTS ix_committee_documents_entity")
    for col in ("entity_type", "entity_id"):
        op.execute(f"ALTER TABLE committee_documents DROP COLUMN IF EXISTS {col}")
    for col in ("is_resolution", "resolution_ref", "resolved_at"):
        op.execute(f"ALTER TABLE meeting_motions DROP COLUMN IF EXISTS {col}")
    for col in ("objective_id", "budget_estimate", "actual_expenditure", "percent_complete",
                "start_date", "closed_by_member_id", "outcome_notes", "meeting_id", "motion_id"):
        op.execute(f"ALTER TABLE committee_tasks DROP COLUMN IF EXISTS {col}")
    op.execute("DROP TABLE IF EXISTS club_objectives")
