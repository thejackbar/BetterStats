"""Add capabilities array to club_memberships

Revision ID: 031
Revises: 030
Create Date: 2026-05-25

Introduces capability-based permissions. Each membership gets a
JSONB array of capability strings; an empty/NULL array means
"use role default" (super_admin and club_admin both get all
capabilities by virtue of role; club_member uses the array as an
explicit allowlist).
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '031'
down_revision = '030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('club_memberships', sa.Column(
        'capabilities',
        postgresql.JSONB(astext_type=sa.Text()),
        server_default=sa.text("'[]'::jsonb"),
        nullable=False,
    ))


def downgrade() -> None:
    op.drop_column('club_memberships', 'capabilities')
