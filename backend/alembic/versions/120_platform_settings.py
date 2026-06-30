"""Platform settings — global super-admin General Settings

A single-row table holding platform-wide settings a super admin manages from the
All Clubs page (Better HQ → General Settings). First field: default_trial_days (the
trial length used when a module trial is created). Stored as a JSONB blob so new
settings can be added without a migration. Enforced single row (id = 1).

Mirrored idempotently in main.py lifespan.

Revision ID: 120
Revises: 119
Create Date: 2026-06-30
"""
from alembic import op


revision = '120'
down_revision = '119'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
            settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "INSERT INTO platform_settings (id, settings) VALUES (1, '{\"default_trial_days\": 14}') "
        "ON CONFLICT (id) DO NOTHING"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS platform_settings")
