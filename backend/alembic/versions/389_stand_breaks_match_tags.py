"""Unbroken and retired partnerships a club types, club match tags for premierships, and a match link on a
hand-typed partnership record

Defined once in services/stand_breaks_ddl.py, which main.py's lifespan mirror also runs.
The view re-issue comes from services/superseded_ddl, which owns v_effective_partnerships.

Revision ID: 389
Revises: 388
"""
from alembic import op

from app.services import superseded_ddl
from app.services.stand_breaks_ddl import DOWNGRADE, STATEMENTS

revision = "389"
down_revision = "388"
branch_labels = None
depends_on = None


def _partnership_view() -> str:
    return next(s for s in superseded_ddl.PER_INNINGS_VIEWS
                if "VIEW v_effective_partnerships " in s)


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)
    op.execute(_partnership_view())


def downgrade() -> None:
    # The view selects is_unbroken: put it back without the column first. CREATE OR REPLACE
    # cannot remove a column, so it is dropped and re-created with the earlier list.
    op.execute("DROP VIEW IF EXISTS v_effective_partnerships")
    op.execute(_partnership_view().replace(", t.is_unbroken", ""))
    op.execute("ALTER TABLE partnerships DROP COLUMN IF EXISTS is_unbroken")
    op.execute("ALTER TABLE manual_partnerships DROP COLUMN IF EXISTS is_unbroken")
    for statement in DOWNGRADE:
        op.execute(statement)
