"""Stats by competition, and the association a grade is played under

A club's stats could be scoped to a season, a grade, a grade CATEGORY and a
match FORMAT, and to nothing about who runs the competition. That is fine for
a club whose whole programme is one association's grades, and wrong for the
ones this was reported from: Applecross plays 2025/26 across three
associations at once, and Hamilton Veterans field one team in several
competitions of the SAME association in one season.

The association comes straight from Cricket Australia and costs no extra
call. The competition is the club's own named group of grades, because CA
does not publish one — see services/competition_ddl.py for the evidence.

Revision ID: 282
Revises: 281
Create Date: 2026-09-01
"""
from alembic import op

from app.services.competition_ddl import DOWNGRADE, STATEMENTS  # noqa: E402

revision = "282"
down_revision = "281"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
