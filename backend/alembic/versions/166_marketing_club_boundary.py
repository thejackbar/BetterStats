"""Marketing club directory — cached suburb boundary polygon

The Club Directory's location map used to only draw an approximate shaded
circle around a club's coordinates — there's no real Australian postcode
boundary dataset in this app. Adds `boundary_geojson` (nullable JSONB) on
`marketing_clubs`, fetched on demand from OpenStreetMap/Nominatim (a
suburb-level admin boundary, the closest free approximation to "the
postcode area") the first time a club's detail panel is opened, and cached
here forever after. `NULL` = never looked up; `{}` = looked up, nothing
found; otherwise a real GeoJSON Polygon/MultiPolygon.

Revision ID: 166
Revises: 165
Create Date: 2026-07-22
"""
from alembic import op


revision = '166'
down_revision = '165'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs ADD COLUMN IF NOT EXISTS boundary_geojson JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE marketing_clubs DROP COLUMN IF EXISTS boundary_geojson")
