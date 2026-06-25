"""Marketing crawl — runtime stop/start control

A single-row flag the crawl loops poll, so an operator can stop the background
crawler at runtime (and resume it) without editing env / recreating the
container. Persisted so a Stop survives a restart — the continuous runner checks
it on every loop and idles while paused.

Revision ID: 100
Revises: 099
Create Date: 2026-06-25
"""
from alembic import op
import sqlalchemy as sa


revision = '100'
down_revision = '099'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'marketing_crawl_control',
        sa.Column('id', sa.SmallInteger(), primary_key=True),
        sa.Column('paused', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint('id = 1', name='marketing_crawl_control_singleton'),
    )
    op.execute("INSERT INTO marketing_crawl_control (id, paused) VALUES (1, FALSE) "
               "ON CONFLICT (id) DO NOTHING")


def downgrade() -> None:
    op.drop_table('marketing_crawl_control')
