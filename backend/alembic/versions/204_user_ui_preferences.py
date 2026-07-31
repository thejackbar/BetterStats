"""Per-user UI preferences store

Adds ``users.ui_preferences`` (JSONB, default ``{}``) — a small per-account
namespace bag so a super admin's UI choices survive across sessions and
devices (localStorage is per-browser only). The first consumer is the CRM
Sales Pipeline stage filter buttons (namespace ``crm_stage_filters``); the
store is generic so other pages can persist their own namespaced state without
another migration.

Non-breaking: additive column with an empty-object default.

Revision ID: 204
Revises: 203
Create Date: 2026-07-31
"""
from alembic import op


revision = "204"
down_revision = "203"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE users ADD COLUMN IF NOT EXISTS "
        "ui_preferences JSONB NOT NULL DEFAULT '{}'::jsonb"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS ui_preferences")
