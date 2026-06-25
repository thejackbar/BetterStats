"""Marketing — association registry (for the automatic roster sweep)

Every Australian cricket association (from the PlayHQ search ASSOCIATION type),
so the background runner can resolve each one's full club roster on a schedule
without an operator clicking. ``id`` is the PlayHQ routingCode (what the roster
traversal keys on); ``last_resolved_at`` drives the sweep + a periodic refresh.

Revision ID: 102
Revises: 101
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


revision = '102'
down_revision = '101'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'marketing_associations',
        sa.Column('id', sa.Text(), primary_key=True),     # PlayHQ routingCode
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('club_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('last_resolved_at', sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column('first_seen_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index('idx_marketing_assoc_resolve', 'marketing_associations', ['last_resolved_at'])


def downgrade() -> None:
    op.drop_index('idx_marketing_assoc_resolve', table_name='marketing_associations')
    op.drop_table('marketing_associations')
