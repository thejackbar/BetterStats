"""BetterSelect — self-service player availability (magic link + last-4 PIN).

Lets players set their own availability for upcoming fixtures without an account,
app, or Facebook integration. Two additions:

  * organisations gains a per-club self-service link. ``availability_link_token``
    is the link's only secret — it's pinned publicly (group chat / QR), so it's
    low-trust by design and **rotatable**. ``availability_self_service_enabled``
    is the on/off switch; ``availability_require_pin`` keeps the last-4-of-phone
    PIN gate on (a club can turn it off so picking a name is enough).
  * player_availability gains ``source`` ('admin' | 'self'). recorded_by is a
    *user* FK and is NULL for a self-reported answer, so ``source`` is what tells
    a player's answer apart from an admin's and gives the admin an audit trail.

Non-breaking: every existing org defaults to disabled (no token), every existing
availability row defaults to source='admin'.

Revision ID: 068
Revises: 067
Create Date: 2026-06-04

"""
from alembic import op
import sqlalchemy as sa


revision = '068'
down_revision = '067'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('organisations', sa.Column('availability_link_token', sa.Text(), nullable=True))
    op.add_column(
        'organisations',
        sa.Column('availability_self_service_enabled', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    op.add_column(
        'organisations',
        sa.Column('availability_require_pin', sa.Boolean(), nullable=False, server_default=sa.text('true')),
    )
    # The token is the public identity of a club's self-service page, so it must
    # be globally unique. Partial index (NULLs excluded) so every not-yet-enabled
    # club can sit at NULL without colliding.
    op.create_index(
        'uq_org_availability_token',
        'organisations',
        ['availability_link_token'],
        unique=True,
        postgresql_where=sa.text('availability_link_token IS NOT NULL'),
    )

    op.add_column(
        'player_availability',
        sa.Column('source', sa.Text(), nullable=False, server_default='admin'),
    )


def downgrade() -> None:
    op.drop_column('player_availability', 'source')
    op.drop_index('uq_org_availability_token', table_name='organisations')
    op.drop_column('organisations', 'availability_require_pin')
    op.drop_column('organisations', 'availability_self_service_enabled')
    op.drop_column('organisations', 'availability_link_token')
