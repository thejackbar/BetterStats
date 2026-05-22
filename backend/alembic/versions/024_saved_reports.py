"""Add saved_reports table for StatLab

Revision ID: 024
Revises: 023
Create Date: 2026-05-22
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '024'
down_revision = '023'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'saved_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organisations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('owner_user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('title', sa.Text(), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('query_json', postgresql.JSONB(), nullable=False),
        sa.Column('visibility', sa.Text(), nullable=False, server_default='club'),
        sa.Column('view_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('org_id', 'slug', name='uq_saved_reports_org_slug'),
    )
    op.create_index('ix_saved_reports_org_id', 'saved_reports', ['org_id'])


def downgrade():
    op.drop_index('ix_saved_reports_org_id', 'saved_reports')
    op.drop_table('saved_reports')
