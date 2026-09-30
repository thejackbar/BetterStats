"""Club teaser snapshots

One JSON snapshot per Club Directory club, pulled from a few cheap Cricket
Australia season-aggregate and ladder calls, so a prospect can be shown their
own club's dashboard (email image, landing page, Meta ad click-through) before
they have registered. Owns no organisation, player or game rows.

Runs services/club_teaser_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 314
Revises: 313
"""
from alembic import op

from app.services.club_teaser_ddl import STATEMENTS, DOWNGRADE

revision = "314"
down_revision = "313"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
