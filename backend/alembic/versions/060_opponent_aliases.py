"""BetterIQ: opponent_aliases — manual fixture-opponent → club links

When a fixture's free-text opponent_name doesn't auto-match a club in our game
history (e.g. "Bassendean" vs stored "Bassendean Cricket Club"), the user can
manually match it on the Opposition screen. That association is persisted here
so every current and future fixture with that name resolves to the chosen
opp_key. Keyed on the lowercased alias name per org.

Revision ID: 060
Revises: 059
Create Date: 2026-06-02

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '060'
down_revision = '059'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'opponent_aliases',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), nullable=False),
        sa.Column('alias_name', sa.Text(), nullable=False),   # lowercased fixture opponent_name
        sa.Column('opp_key', sa.Text(), nullable=False),
        sa.Column('display_name', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['organisation_id'], ['organisations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organisation_id', 'alias_name', name='uq_opponent_alias_org_name'),
    )


def downgrade() -> None:
    op.drop_table('opponent_aliases')
