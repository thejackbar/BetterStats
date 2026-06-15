"""BetterMerch — club stock register (BetterAdmin module)

Four tables, all org-scoped:

  - merch_products   — the catalogue line (the 'what'); category picks the template
  - merch_variants   — the stock-keeping line (size/colour, or 'Standard'); on-hand
                       quantity lives here as a running balance
  - merch_movements  — the in/out audit log; signed delta + optional player link and
                       paid/unpaid for a sale or issue (merch owings, separate from fees)
  - merch_assets     — individual high-value equipment with condition + service/replace
                       dates for cashflow

Mirrored idempotently in main.py's lifespan so the API boots before alembic runs.

Revision ID: 083
Revises: 082
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '083'
down_revision = '082'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'merch_products',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('category', sa.Text(), nullable=False, server_default='apparel'),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('low_stock_threshold', sa.Integer(), nullable=True),
        sa.Column('supplier', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_merch_products_org', 'merch_products', ['organisation_id', 'category'])

    op.create_table(
        'merch_variants',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('product_id', UUID(as_uuid=True), sa.ForeignKey('merch_products.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('label', sa.Text(), nullable=False, server_default='Standard'),
        sa.Column('size', sa.Text(), nullable=True),
        sa.Column('colour', sa.Text(), nullable=True),
        sa.Column('sku', sa.Text(), nullable=True),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('low_stock_threshold', sa.Integer(), nullable=True),
        sa.Column('expiry_date', sa.Date(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_merch_variants_product', 'merch_variants', ['product_id'])
    op.create_index('ix_merch_variants_org', 'merch_variants', ['organisation_id'])

    op.create_table(
        'merch_movements',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('variant_id', UUID(as_uuid=True), sa.ForeignKey('merch_variants.id', ondelete='CASCADE'), nullable=False),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('kind', sa.Text(), nullable=False, server_default='adjustment'),
        sa.Column('delta', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('quantity_after', sa.Integer(), nullable=True),
        sa.Column('unit_cost', sa.Numeric(10, 2), nullable=True),
        sa.Column('unit_price', sa.Numeric(10, 2), nullable=True),
        sa.Column('player_id', UUID(as_uuid=True), sa.ForeignKey('players.id', ondelete='SET NULL'), nullable=True),
        sa.Column('amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('paid', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('paid_at', sa.Date(), nullable=True),
        sa.Column('payment_method', sa.Text(), nullable=True),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('occurred_on', sa.Date(), nullable=True),
        sa.Column('created_by_user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_merch_movements_variant', 'merch_movements', ['variant_id', 'created_at'])
    op.create_index('ix_merch_movements_org', 'merch_movements', ['organisation_id'])
    op.create_index('ix_merch_movements_player', 'merch_movements', ['player_id'])

    op.create_table(
        'merch_assets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('asset_tag', sa.Text(), nullable=True),
        sa.Column('purchase_cost', sa.Numeric(10, 2), nullable=True),
        sa.Column('purchase_date', sa.Date(), nullable=True),
        sa.Column('condition', sa.Text(), nullable=False, server_default='good'),
        sa.Column('service_due_date', sa.Date(), nullable=True),
        sa.Column('replace_due_date', sa.Date(), nullable=True),
        sa.Column('status', sa.Text(), nullable=False, server_default='in_service'),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_merch_assets_org', 'merch_assets', ['organisation_id'])


def downgrade() -> None:
    op.drop_table('merch_assets')
    op.drop_table('merch_movements')
    op.drop_table('merch_variants')
    op.drop_table('merch_products')
