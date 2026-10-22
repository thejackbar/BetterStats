"""A player can update their own contact details: address and emergency contact.

`players.address_line1`, `suburb`, `state`, `postcode`, `emergency_contact_name`,
`emergency_contact_phone` (all nullable text). Email and mobile already exist.

Runs services/player_contact_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 356
Revises: 355
"""
from alembic import op

from app.services.player_contact_ddl import STATEMENTS, DOWNGRADE

revision = "356"
down_revision = "355"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
