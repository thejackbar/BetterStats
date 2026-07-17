"""First-touch signup attribution on organisations, for the public
self-serve trial flow (Meta ad campaign).

A club that registers itself through the public /trial page carries the
browser's first-touch acquisition record (frontend/src/lib/visitor.js
getAttribution(): UTM tags, ad-network click id, landing path/referrer)
into the registration submit. Stored verbatim here so ad performance can be
joined against what the club later does (trial usage, Twenty engagement
score, conversion to paid) — see the ad-signups report in routers/meta_ads.py.

signup_source is the coarse bucket for filtering ('self_serve_ad' when the
attribution carried a real campaign/click signal, 'self_serve_organic'
otherwise); signup_attribution is the full raw payload.

Revision ID: 160
Revises: 159
Create Date: 2026-07-17
"""
from alembic import op


revision = '160'
down_revision = '159'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS signup_source TEXT")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS signup_attribution JSONB")


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS signup_source")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS signup_attribution")
