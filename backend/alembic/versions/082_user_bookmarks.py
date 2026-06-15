"""user_bookmarks — per-user quick-access favourites in the admin nav.

Each admin user can star the pages they visit most so they sit at the top of
the sidebar for one-tap access (mirrors HubSpot's Bookmarks). Bookmarks are
keyed to the user, not the club: the admin routes are the same whichever club a
super admin is acting as, so the same favourites follow them across clubs.

ON DELETE CASCADE so deleting a user clears their bookmarks. Additive +
idempotent; nothing else reads the table, so it is inert until the UI uses it.

Revision ID: 082
Revises: 081
Create Date: 2026-06-15

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


revision = '082'
down_revision = '081'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'user_bookmarks',
        sa.Column('id', UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', UUID(as_uuid=True), nullable=False),
        sa.Column('path', sa.Text(), nullable=False),
        sa.Column('label', sa.Text(), nullable=False),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'path', name='uq_user_bookmark_path'),
    )


def downgrade() -> None:
    op.drop_table('user_bookmarks')
