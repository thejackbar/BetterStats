"""Extra onboarding questions on the public Contact form.

The marketing Contact form (betterstats.cricket/contact) absorbed the questions
that used to live on the standalone Google Form, so the Google Form can be
retired. These columns store the new answers alongside the existing ones on
``club_onboarding_requests``: the sender's role, the club's founding year,
whether the club's data is in PlayHQ, whether they hold historical data, what
they're most interested in (comma-joined), how they heard about us, and their
preferred contact method.

All nullable and additive. Mirrored idempotently in the main.py lifespan.

Revision ID: 081
Revises: 080
Create Date: 2026-06-11

"""
from alembic import op


revision = '081'
down_revision = '080'
branch_labels = None
depends_on = None


_COLUMNS = (
    "role", "founded_year", "playhq_status", "has_historical",
    "interests", "heard_about", "contact_method",
)


def upgrade() -> None:
    for col in _COLUMNS:
        op.execute(f"ALTER TABLE club_onboarding_requests ADD COLUMN IF NOT EXISTS {col} TEXT")


def downgrade() -> None:
    for col in _COLUMNS:
        op.execute(f"ALTER TABLE club_onboarding_requests DROP COLUMN IF EXISTS {col}")
