"""Daily product update: mark notes written afterwards for past days

``product_blasts.backfilled`` is TRUE for a note written from the release history for a day
that has already gone by. It shows on the What's New page and is never raised as a
notification. The DDL lives once in ``services/product_blast_ddl.py``. Idempotent.

Revision ID: 354
Revises: 353
"""
from alembic import op

from app.services.product_blast_ddl import BACKFILL_STATEMENTS  # noqa: E402

revision = "354"
down_revision = "353"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for stmt in BACKFILL_STATEMENTS:
        op.execute(stmt)


def downgrade() -> None:
    op.execute("ALTER TABLE product_blasts DROP COLUMN IF EXISTS backfilled")
