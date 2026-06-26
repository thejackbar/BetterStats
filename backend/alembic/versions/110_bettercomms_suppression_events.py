"""BetterComms Phase 1 — global suppression + email events + per-person prefs

The delivery + suppression foundation for BetterComms (see
docs/bettercomms-architecture.md):

- ``email_suppressions`` — the ONE piece of global, address-level state. A hard
  bounce or a spam complaint is a fact about the mailbox, not a club, so it lives
  here keyed on the email and blocks that address across every club's sends.
- ``email_events`` — append-only audit of every SES event (delivered / bounce /
  complaint / reject / delay / open / click), tied back to the person + campaign
  via the recipient's provider_message_id. Deduped on (ses_message_id,
  event_type, email).
- per-club ``complained`` state on ``comms_contacts`` (mirrors the existing
  ``bounced``), plus a ``preferences`` JSONB for per-person, per-category opt-outs
  (transactional / operational / news / marketing).

Everything else (unsubscribe, preferences, tags, lists) stays per club; only the
suppression table is global. Mirrored idempotently in main.py lifespan.

Revision ID: 110
Revises: 109
Create Date: 2026-06-26
"""
from alembic import op


revision = '110'
down_revision = '109'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_suppressions (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email TEXT NOT NULL,
            reason TEXT NOT NULL,            -- hard_bounce | complaint | manual
            source TEXT,                     -- ses | admin | import
            detail TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_email_suppressions_email UNIQUE (email)
        )
    """)
    op.execute("""
        CREATE TABLE IF NOT EXISTS email_events (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
            campaign_id UUID REFERENCES comms_campaigns(id) ON DELETE SET NULL,
            recipient_id UUID REFERENCES comms_recipients(id) ON DELETE SET NULL,
            contact_id UUID REFERENCES comms_contacts(id) ON DELETE SET NULL,
            email TEXT,
            event_type TEXT NOT NULL,        -- delivery | bounce | complaint | reject | deliverydelay | open | click | send
            event_subtype TEXT,              -- Permanent / Transient, etc.
            reason TEXT,
            ses_message_id TEXT,
            payload JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_email_event_dedupe UNIQUE (ses_message_id, event_type, email)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_events_org ON email_events(organisation_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_events_campaign ON email_events(campaign_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_email_events_email ON email_events(lower(email))")
    op.execute("ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS complained BOOLEAN NOT NULL DEFAULT FALSE")
    op.execute("ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS complained_at TIMESTAMPTZ")
    op.execute("ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS preferences JSONB NOT NULL DEFAULT '{}'")


def downgrade() -> None:
    op.execute("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS preferences")
    op.execute("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS complained_at")
    op.execute("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS complained")
    op.execute("DROP TABLE IF EXISTS email_events")
    op.execute("DROP TABLE IF EXISTS email_suppressions")
