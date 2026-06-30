"""Index organisations(slug) for the Club Directory visit→club resolution

The "visited the site" filter / visit stats resolve each page_view to a club, and
one branch probes organisations by slug (`o.slug = <path slug>`). marketing_clubs
(utm_code) and marketing_utm_aliases (utm_value) were already indexed; organisations
(slug) was not. Adds it.

Mirrored idempotently in main.py lifespan.

Revision ID: 121
Revises: 120
Create Date: 2026-06-30
"""
from alembic import op


revision = '121'
down_revision = '120'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE INDEX IF NOT EXISTS idx_organisations_slug ON organisations(slug)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_organisations_slug")
