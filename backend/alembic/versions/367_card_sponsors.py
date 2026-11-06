"""The sponsor a club shows on its player cards.

`organisations.card_sponsors` holds only what a club picked, one sponsor for the
public share card and one for the collectable Player Cards. Which sponsor a card
shows is derived on read (the pick, else the top sponsor with a logo).

Runs services/card_sponsors_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 367
Revises: 366
"""
from alembic import op

from app.services.card_sponsors_ddl import STATEMENTS, DOWNGRADE

revision = "367"
down_revision = "366"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
