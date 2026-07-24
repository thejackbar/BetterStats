"""BetterCRM sales targets (clubs won / ARR / revenue / trials / conversion)

Revision ID: 185
Revises: 184
Create Date: 2026-07-24
"""
from alembic import op

revision = '185'
down_revision = '184'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS crm_targets (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            period_type TEXT NOT NULL,
            period_key TEXT NOT NULL,
            target_clubs_won INTEGER,
            target_arr_cents BIGINT,
            target_revenue_cents BIGINT,
            target_trials INTEGER,
            target_conversion_rate INTEGER,
            notes TEXT,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            UNIQUE (period_type, period_key)
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS crm_targets")
