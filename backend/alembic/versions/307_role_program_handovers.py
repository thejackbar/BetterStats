"""Role Program handovers — the measurable, succession-planning half of a role.

A club's Role Program (what a role entails) is assembled on read from the role,
its Club Diary tasks (whose cadence set is widened in the same release to cover
weekly / matchday / season start / season end / ongoing) and its roster areas,
so it needs no storage. What IS stored is the onboarding checklist a responsible
person works when a role changes hands: per element, has the new volunteer been
walked through it, and have they understood and accepted it. Two tables, both
defined once in services/role_program_ddl.py and shared with the lifespan
mirror per the vote_medal_ddl rule.

Revision ID: 307
Revises: 306
"""
from alembic import op

from app.services.role_program_ddl import STATEMENTS

revision = "307"
down_revision = "306"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    # Items first (FK to handovers). The Diary cadence widening is Python-only
    # (frequency is a plain TEXT column, no CHECK), so there is nothing to undo
    # there.
    op.execute("DROP TABLE IF EXISTS role_program_handover_items")
    op.execute("DROP TABLE IF EXISTS role_program_handovers")
