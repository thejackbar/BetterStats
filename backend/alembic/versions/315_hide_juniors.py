"""Hide a club's junior programme from its public Stats.

`club_competitions.is_junior` tags a competition (a named group of a club's
grades, seeded one per association) as junior or senior; NULL falls back to a
guess from its name. `organisations.hide_juniors` is the club's switch, off by
default. Nothing about who is hidden is stored: it is derived on read.

Runs services/junior_hiding_ddl.STATEMENTS, the same list main.py's lifespan
runs. Every statement is idempotent.

Revision ID: 315
Revises: 314
"""
from alembic import op

from app.services.junior_hiding_ddl import STATEMENTS, DOWNGRADE

revision = "315"
down_revision = "314"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
