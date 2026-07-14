"""Add password_reset_token / password_reset_token_expires_at to users.

Lets a club admin send an existing club-user account a "reset your password"
email link (routers/club_admin.py::send_password_reset_link) — distinct from
the invite_token/invite_token_expires_at pair added in migration 141, which
is only for a brand-new account's first-ever password (that flow 404s once
password_hash is already set). See app/models/db.py::User.

Revision ID: 144
Revises: 143
Create Date: 2026-07-14
"""
from alembic import op


revision = '144'
down_revision = '143'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token TEXT UNIQUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS password_reset_token_expires_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_token_expires_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS password_reset_token")
