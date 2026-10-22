"""Daily product update: the log of each day's post and the Stop switch

A daily summary of client-facing changes, written from the changelog and posted to
each club's notifications at 9am Melbourne time. This adds the log table
(``product_blasts``) and the one-row Stop switch (``product_blast_control``, which starts
stopped). The DDL lives once in ``services/product_blast_ddl.py``; the lifespan mirror in
main.py runs the same list. Idempotent.

Revision ID: 353
Revises: 352
"""
from alembic import op

from app.services.product_blast_ddl import DOWNGRADE, STATEMENTS  # noqa: E402

revision = "353"
down_revision = "352"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    for stmt in DOWNGRADE:
        op.execute(stmt)
