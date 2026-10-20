"""A club's own names for its public sections, optionally linked to a sponsor.

`organisations.section_names` holds only the sections a club renamed (for
example Fantasy becoming "Froth Fantasy Cricket"), each with an optional
sponsor id. NULL means every section keeps its standard name.

Runs services/section_names_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 319
Revises: 318
"""
from alembic import op

from app.services.section_names_ddl import STATEMENTS, DOWNGRADE

revision = "319"
down_revision = "318"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
