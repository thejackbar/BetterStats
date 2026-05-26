"""Add status column to saved_reports for admin approval flow.

Revision ID: 032
Revises: 031
Create Date: 2026-05-26

Club-visibility reports now require admin approval before they're listed on
the public StatLab page. Private reports skip the approval flow and are
auto-approved on save. Backfills existing rows as 'approved' so nothing
disappears for active clubs.
"""
from alembic import op
import sqlalchemy as sa


revision = '032'
down_revision = '031'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'saved_reports',
        sa.Column('status', sa.Text(), nullable=False, server_default='approved'),
    )
    op.add_column(
        'saved_reports',
        sa.Column('reviewed_by_user_id', sa.dialects.postgresql.UUID(as_uuid=True),
                  sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )
    op.add_column(
        'saved_reports',
        sa.Column('reviewed_at', sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.add_column(
        'saved_reports',
        sa.Column('review_note', sa.Text(), nullable=True),
    )
    op.create_index('ix_saved_reports_status', 'saved_reports', ['status'])


def downgrade() -> None:
    op.drop_index('ix_saved_reports_status', 'saved_reports')
    op.drop_column('saved_reports', 'review_note')
    op.drop_column('saved_reports', 'reviewed_at')
    op.drop_column('saved_reports', 'reviewed_by_user_id')
    op.drop_column('saved_reports', 'status')
