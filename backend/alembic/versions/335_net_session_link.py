"""A net session's own check-in link, and the squads it is for.

`net_sessions.checkin_token` (unique, NULL until first asked for) and
`net_sessions.squad_team_ids` (NULL = everyone). Existing sessions behave as
before.

Runs services/net_session_link_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 335
Revises: 334
"""
from alembic import op

from app.services.net_session_link_ddl import STATEMENTS, DOWNGRADE

revision = "335"
down_revision = "334"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
