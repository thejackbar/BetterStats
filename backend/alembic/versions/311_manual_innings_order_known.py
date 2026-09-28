"""Whether an imported match's batting order is known

A club scorebook such as CSFW records our innings and the opposition's innings
total for every match, and never which of the two was batted first. Importing
those totals needs somewhere to say so, or the match page labels the innings
"Innings 1" and "Innings 2" and works out a "won by N wickets" from an order
nobody recorded.

`manual_games.innings_order_known` is NULL for every existing game (the order
is known, or there is only one innings) and FALSE for an import that said it
does not know. Re-runs the whole shared list, which is idempotent, so the same
code path covers a fresh database and one already at 310. The downgrade drops
the COLUMN only: 310 owns the table.

Revision ID: 311
Revises: 310
"""
from alembic import op

from app.services.manual_innings_ddl import STATEMENTS, DOWNGRADE_311

revision = "311"
down_revision = "310"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE_311:
        op.execute(statement)
