"""Card review: the club's choice between a match's two stored versions, with history

Adds ``manual_games.review_choice`` (and who, when, why) and the ``card_review_log`` table.
Nothing changes for a match nobody has reviewed: every new column is NULL or FALSE.

Defined once in services/card_review_ddl.py, which main.py's lifespan mirror also runs.
Idempotent.

Revision ID: 350
Revises: 349
"""
from alembic import op

from app.services.card_review_ddl import STATEMENTS, DOWNGRADE

revision = "350"
down_revision = "349"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    for statement in DOWNGRADE:
        op.execute(statement)
