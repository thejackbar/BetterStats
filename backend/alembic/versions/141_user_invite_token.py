"""Add invite_token / invite_token_expires_at to users.

The club-user "Invite admin" flow (routers/club_admin.py::create_club_user)
can now create an account with no usable password yet (password_hash was
already nullable) plus a random token, emailed as a set-your-password link.
See app/models/db.py::User for the full rationale.

Revision ID: 141
Revises: 140
Create Date: 2026-07-14
"""
from alembic import op


revision = '141'
down_revision = '140'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_token TEXT UNIQUE")
    op.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS invite_token_expires_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS invite_token_expires_at")
    op.execute("ALTER TABLE users DROP COLUMN IF EXISTS invite_token")
