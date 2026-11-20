"""Association socials workspaces: `organisations.workspace_kind`.

NULL for a club, 'association' for a BetterSocials-only workspace that builds posts for a
whole grade from a pasted link. Runs services/association_workspace_ddl.STATEMENTS, the same
list main.py's lifespan runs. Every statement is idempotent.

Revision ID: 392
Revises: 391
"""
from alembic import op

from app.services.association_workspace_ddl import STATEMENTS, DOWNGRADE

revision = "392"
down_revision = "391"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
