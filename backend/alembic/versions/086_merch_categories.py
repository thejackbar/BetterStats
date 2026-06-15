"""BetterMerch — club-defined category tree (categories + sub-categories)

A self-referencing `merch_categories` tree (up to three levels) per club, nested
under the fixed top type, plus `merch_products.category_id` to file an item under
a node. Created inline as items are added; reports roll up by node.

Mirrored idempotently in main.py's lifespan.

Revision ID: 086
Revises: 085
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '086'
down_revision = '085'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'merch_categories',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('organisation_id', UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('parent_id', UUID(as_uuid=True), sa.ForeignKey('merch_categories.id', ondelete='CASCADE'), nullable=True),
        sa.Column('top_category', sa.Text(), nullable=False),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_merch_categories_org', 'merch_categories', ['organisation_id', 'top_category', 'parent_id'])
    op.add_column('merch_products', sa.Column('category_id', UUID(as_uuid=True),
                  sa.ForeignKey('merch_categories.id', ondelete='SET NULL'), nullable=True))


def downgrade() -> None:
    op.drop_column('merch_products', 'category_id')
    op.drop_index('ix_merch_categories_org', table_name='merch_categories')
    op.drop_table('merch_categories')
