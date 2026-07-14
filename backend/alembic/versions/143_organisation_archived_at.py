"""Add organisations.archived_at (soft-delete / archive).

The Super Admin "Delete Club" action used to be a permanent, unreversible
hard delete. Adds a nullable timestamp so it can archive instead — see
app/models/db.py::Organisation for the full rationale.

Revision ID: 143
Revises: 142
Create Date: 2026-07-14
"""
from alembic import op


revision = '143'
down_revision = '142'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS archived_at TIMESTAMPTZ")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS archived_at")
