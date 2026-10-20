"""Votes: a tied week is settled on countback by default

A weekly 3-2-1 that ends level used to share the higher points under the default
``tie_policy`` 'share', which handed out more points than the ballot holds. New medals now
default to 'countback' and every existing medal still on 'share' moves to it. Only a dead heat
after every countback still shares. A club can choose "Allow ties" again afterwards on the
Settings tab; this runs once, so that later choice is kept.

Only the column default and a one-off data update, so no entry in the lifespan mirror (it would
overwrite a club's later choice on every boot). Idempotent.

Revision ID: 352
Revises: 351
"""
from alembic import op

revision = "352"
down_revision = "351"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE vote_medals ALTER COLUMN tie_policy SET DEFAULT 'countback'")
    op.execute("UPDATE vote_medals SET tie_policy = 'countback' WHERE tie_policy = 'share'")


def downgrade() -> None:
    # The data move is not reversed: the earlier value cannot be told from a club's own choice.
    op.execute("ALTER TABLE vote_medals ALTER COLUMN tie_policy SET DEFAULT 'share'")
