"""Player Dashboard registration: smart matching and playing details.

Adds `matched_by`, `playing` and `applied` to `player_registrations`
(services/player_registration_ddl.STATEMENTS_399, which the lifespan also runs),
then once, here only, marks claims v9.152.0 proved with the PIN as approved
(FIX_399).

Revision ID: 399
Revises: 398
"""
from alembic import op

from app.services.player_registration_ddl import DOWNGRADE_399, FIX_399, STATEMENTS_399

revision = "399"
down_revision = "398"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS_399 + FIX_399:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE_399:
        op.execute(stmt)
