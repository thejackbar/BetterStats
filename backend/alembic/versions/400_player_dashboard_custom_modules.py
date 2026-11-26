"""A club's own Player Dashboard modules (links, announcements, events, image banners) and the
order of the dashboard's cards, and how players pay their fees.

The DDL lives once in services/player_dashboard_custom_ddl.py, which main.py's lifespan also runs.

Revision ID: 400
Revises: 399
"""
from alembic import op

from app.services.player_dashboard_custom_ddl import DOWNGRADE, STATEMENTS

revision = "400"
down_revision = "399"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
