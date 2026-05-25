"""Add notification tracking fields to users

Revision ID: 029
Revises: 028
Create Date: 2026-05-24
"""
from alembic import op
import sqlalchemy as sa

revision = '029'
down_revision = '028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column(
        'last_notification_seen_at',
        sa.TIMESTAMP(timezone=True),
        nullable=True,
    ))
    op.add_column('users', sa.Column(
        'last_seen_app_version',
        sa.Text(),
        nullable=True,
    ))


def downgrade() -> None:
    op.drop_column('users', 'last_seen_app_version')
    op.drop_column('users', 'last_notification_seen_at')
