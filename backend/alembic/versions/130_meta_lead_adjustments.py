"""Meta Ads — manual leads adjustment log

Meta's self-reported ``leads`` figure (Graph API ad-account actions) is
explicitly "indicative" — the HQ page already says the real conversions are
the onboarding list. Operators reconcile the two by hand. Rather than
overwriting the Meta-sourced number (which would get stomped by the next
daily snapshot / Refresh now, since ``run_snapshot`` upserts ``leads`` fresh
from the API every time), the correction is stored as a signed delta log:
effective leads = latest snapshot's raw ``leads`` + SUM(delta) here.

Revision ID: 130
Revises: 129
Create Date: 2026-07-03
"""
from alembic import op


revision = '130'
down_revision = '129'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS meta_lead_adjustments (
            id BIGSERIAL PRIMARY KEY,
            delta INTEGER NOT NULL,
            note TEXT,
            created_by_email TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_meta_lead_adjustments_created_at "
        "ON meta_lead_adjustments(created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS meta_lead_adjustments")
