"""BetterMerch — Square POS integration (canteen/bar stock + sales)

Adds the per-club Square OAuth connection table plus the Square-mapping columns
on the merch tables:

  - merch_products.source / .square_object_id   (Square catalog ITEM id)
  - merch_variants.square_object_id             (Square ITEM_VARIATION id)
  - merch_movements.source / .external_ref      (dedupe imported rows)
  - merch_square_connections                    (one OAuth connection per club)

Mirrored idempotently in main.py's lifespan.

Revision ID: 084
Revises: 083
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '084'
down_revision = '083'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('merch_products', sa.Column('source', sa.Text(), nullable=False, server_default='manual'))
    op.add_column('merch_products', sa.Column('square_object_id', sa.Text(), nullable=True))
    op.add_column('merch_variants', sa.Column('square_object_id', sa.Text(), nullable=True))
    op.add_column('merch_movements', sa.Column('source', sa.Text(), nullable=False, server_default='manual'))
    op.add_column('merch_movements', sa.Column('external_ref', sa.Text(), nullable=True))

    op.create_index('ix_merch_products_square', 'merch_products', ['organisation_id', 'square_object_id'])
    op.create_index('ix_merch_variants_square', 'merch_variants', ['organisation_id', 'square_object_id'])
    op.create_index(
        'uq_merch_movement_external_ref', 'merch_movements',
        ['organisation_id', 'external_ref'], unique=True,
        postgresql_where=sa.text('external_ref IS NOT NULL'),
    )

    op.create_table(
        'merch_square_connections',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('merchant_id', sa.Text(), nullable=True),
        sa.Column('environment', sa.Text(), nullable=False, server_default='production'),
        sa.Column('access_token', sa.Text(), nullable=True),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('location_id', sa.Text(), nullable=True),
        sa.Column('location_name', sa.Text(), nullable=True),
        sa.Column('sync_enabled', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('sync_sales', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('last_sync_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('last_sync_status', sa.Text(), nullable=True),
        sa.Column('last_sync_error', sa.Text(), nullable=True),
        sa.Column('sales_cursor', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('connected_by_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('connected_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint('organisation_id', name='uq_merch_square_org'),
    )


def downgrade() -> None:
    op.drop_table('merch_square_connections')
    op.drop_index('uq_merch_movement_external_ref', table_name='merch_movements')
    op.drop_index('ix_merch_variants_square', table_name='merch_variants')
    op.drop_index('ix_merch_products_square', table_name='merch_products')
    op.drop_column('merch_movements', 'external_ref')
    op.drop_column('merch_movements', 'source')
    op.drop_column('merch_variants', 'square_object_id')
    op.drop_column('merch_products', 'square_object_id')
    op.drop_column('merch_products', 'source')
