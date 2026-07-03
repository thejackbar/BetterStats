"""BetterComms configurable From local-part

Adds organisations.comms_from_local — the local-part of the SES From address,
decoupled from the org slug so a club (or the marketing org) can set a clean
public From without renaming its slug/URL. NULL falls back to the slug.
Idempotent, mirrored in the main.py lifespan.

Revision ID: 128
Revises: 127
"""
from alembic import op

revision = "128"
down_revision = "127"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS comms_from_local TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS comms_from_local")
