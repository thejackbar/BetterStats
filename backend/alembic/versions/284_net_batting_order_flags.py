"""Padding up, and batting early.

Two flags on ``net_attendance``, both reported from a club running its Thursday
nets off an iPad.

``padding_up``
    Who has been told to get their gear on for the next turn, so the screen on
    the fence says it rather than the coach shouting it twice. It is NOT the
    next N names in the queue — the person who pads up is whoever the coach
    actually spoke to, which on a real night is routinely somebody further down
    the list. Transient: cleared when they go into a net, when they are marked
    as batted, and when they leave the rotation.

``priority``
    Needs to bat early tonight — a captain on selection night, somebody leaving
    at seven. It records the fact and NOT a position: ticking it asks the coach
    whether to move them up or just flag it, because a flag that re-sorted the
    queue by itself would undo the order the coach had just dragged into place,
    and several of them at once would leave nobody able to say who is really
    first. The reason goes in the existing ``note``, which already holds what
    somebody said on the way in.

Both default false, so every session already recorded reads exactly as it did.

Revision ID: 284
Revises: 283
"""
from alembic import op

revision = "284"
down_revision = "283"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS "
        "padding_up BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE net_attendance ADD COLUMN IF NOT EXISTS "
        "priority BOOLEAN NOT NULL DEFAULT false"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS priority")
    op.execute("ALTER TABLE net_attendance DROP COLUMN IF EXISTS padding_up")
