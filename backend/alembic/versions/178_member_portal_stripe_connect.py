"""Member self-service portal, Stripe Connect fee payments, reminder automation.

Three features, one migration, all hidden behind the SAME super-admin-only
platform flag (`platform_settings.member_portal_enabled` + the per-club
`organisations.member_portal_override`, exactly mirroring the existing
`billing_checkout_enabled`/`billing_checkout_override` pair) — per direct
instruction, none of this is visible to an ordinary club admin, or usable by
a real member, until a super admin switches it on (globally, or for one test
club first).

- Member portal: a member logs in via an emailed magic link (no shared link,
  no PIN — see services/member_portal_auth.py) to see their own fees,
  qualifications and update their own contact details. No new tables needed
  for the login flow itself (stateless signed JWT, same posture as the
  existing Square/Xero OAuth-state tokens) — this migration only adds the
  organisation-level Stripe Connect columns and two reminder-throttle
  columns.
- Stripe Connect: a SEPARATE Stripe integration from organisations.
  stripe_customer_id/stripe_subscription_id (BetterCricket's own platform
  billing, one Stripe account for the whole platform). Here each club gets
  its own Stripe Express connected account so a member's fee payment lands
  directly in the club's own bank account — see
  services/stripe_connect_client.py. Online payments are recorded as an
  ordinary fee_payments row (source='stripe_connect', external_ref = the
  Stripe payment_intent id, deduped by the EXISTING uq_fee_payment_external_ref
  unique index from migration ~150) — no new payments table.
- Reminder automation: qualification-expiry and fee-owing reminder emails,
  throttled per row so the daily job can run every day without re-sending —
  see services/member_reminders.py.

Revision ID: 178
Revises: 177
Create Date: 2026-07-23
"""
from alembic import op

revision = '178'
down_revision = '177'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS member_portal_override BOOLEAN")
    op.execute("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_account_id TEXT")
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_details_submitted "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_charges_enabled "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS stripe_connect_payouts_enabled "
        "BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE member_qualifications ADD COLUMN IF NOT EXISTS last_reminder_sent_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE fee_member_seasons ADD COLUMN IF NOT EXISTS last_fee_reminder_sent_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE fee_member_seasons DROP COLUMN IF EXISTS last_fee_reminder_sent_at")
    op.execute("ALTER TABLE member_qualifications DROP COLUMN IF EXISTS last_reminder_sent_at")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_connect_payouts_enabled")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_connect_charges_enabled")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_connect_details_submitted")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS stripe_connect_account_id")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS member_portal_override")
