"""public player attribute visibility settings

Per-club toggles controlling which descriptive player attributes appear on the
public /players/:id profile. Overseas remains always-visible; these gate the
player role, batting hand, bowling style, opening-batsman flag and gender so a
club decides how much of a player's profile is exposed to the public.

Revision ID: 054
Revises: 053
Create Date: 2026-05-31

"""
from alembic import op
import sqlalchemy as sa


revision = '054'
down_revision = '053'
branch_labels = None
depends_on = None


_COLS = [
    'public_show_role',
    'public_show_batting',
    'public_show_bowling',
    'public_show_opening',
    'public_show_gender',
]


def upgrade() -> None:
    for col in _COLS:
        op.add_column(
            'organisations',
            sa.Column(col, sa.Boolean(), nullable=False, server_default=sa.text('false')),
        )


def downgrade() -> None:
    for col in _COLS:
        op.drop_column('organisations', col)
