"""Comms templates gain a stable link to their Sales Workspace slot.

The Sales Workspace's "Send an email" dropdown has always resolved its
editable copy of a built-in template by matching ``comms_templates.name``
against a fixed string (``services/sales_email.TEMPLATE_DB_NAMES`` /
``TEMPLATE_LABELS``) -- so renaming "Trial information" in BetterAdmin ->
Comms -> Templates silently broke the link: the dropdown fell back to the
hardcoded default content, and the NEXT load of the Templates screen
reseeded a brand-new row under the original name, leaving the renamed one
orphaned.

``sales_template_key`` is the fix: a stable machine key (one of
``sales_email.BUILT_IN_TEMPLATES`` -- 'information', 'trial_information',
'demo', ...) stored on the row itself, so the Name column is free to be
renamed at any time without touching what the dropdown resolves to.

Backfilled here from the CURRENT name-matching rule, once, for every row
that already exists in the platform's marketing outreach org -- this
reconstructs exactly what the old name-based lookup would have found
today, so nothing that already works stops working. A row whose name had
ALREADY drifted from the expected default before this migration runs was
already falling back to hardcoded content under the old scheme; it stays
that way (no worse off) until an admin re-picks it, at which point the new
column keeps it linked for good.

Nullable and additive only -- every existing template outside the
outreach org (an ordinary club's own BetterComms library) is untouched;
the unique constraint permits any number of NULLs (standard SQL: NULL is
never considered equal to NULL), so it only ever constrains the handful of
sales-linked rows in the one outreach org.

Revision ID: 261
Revises: 260
Create Date: 2026-08-18
"""
from alembic import op
from sqlalchemy import text


revision = '261'
down_revision = '260'
branch_labels = None
depends_on = None

# Mirrors sales_email.py's TEMPLATE_DB_NAMES (falls back to TEMPLATE_LABELS
# for a key with no override) -- the exact name-matching rule being
# retired, reproduced here as plain data so this migration needs no
# application import.
_KEY_TO_NAME = {
    "information": "Send information",
    "voicemail_followup": "Email following voicemail",
    "trial_information": "Trial information",
    "trial_extension": "Sales rep trial extension",
    "demo": "Book a demo",
    "subscribe": "Sales rep subscribe link",
    "custom": "Custom sales rep email",
}


def upgrade() -> None:
    op.execute("ALTER TABLE comms_templates ADD COLUMN IF NOT EXISTS sales_template_key TEXT")
    op.execute("""
        DO $$ BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint WHERE conname = 'uq_comms_template_org_sales_key'
            ) THEN
                ALTER TABLE comms_templates
                    ADD CONSTRAINT uq_comms_template_org_sales_key UNIQUE (organisation_id, sales_template_key);
            END IF;
        END $$;
    """)
    conn = op.get_bind()
    for key, name in _KEY_TO_NAME.items():
        conn.execute(
            text(
                "UPDATE comms_templates SET sales_template_key = :key "
                "WHERE name = :name AND sales_template_key IS NULL "
                "AND organisation_id IN (SELECT id FROM organisations WHERE is_marketing_outreach IS TRUE)"
            ),
            {"key": key, "name": name},
        )


def downgrade() -> None:
    op.execute("ALTER TABLE comms_templates DROP CONSTRAINT IF EXISTS uq_comms_template_org_sales_key")
    op.execute("ALTER TABLE comms_templates DROP COLUMN IF EXISTS sales_template_key")
