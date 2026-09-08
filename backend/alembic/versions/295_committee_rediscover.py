"""Re-read a club's committee from PlayHQ, and carry the role into BetterComms

The Club Directory's committee has only ever grown. ``_store_contact`` upserts
on lower(email) and never removes, so a club that elected a new committee for
the season read as last season's officers PLUS this season's, with nothing on
screen saying which was which.

A Rediscover now re-reads what PlayHQ publishes and reconciles against it.
``former_at`` is what lets that be safe: an officer PlayHQ no longer lists is
deleted where nothing would be lost, and kept with ``former_at`` stamped where
a person has decided something about them. Deleting an unsubscribed officer is
the case that matters — the next crawl would re-add them subscribed and ticked,
and we would email somebody who opted out.

``comms_contacts.role`` is the other half. An officer already in BetterComms
gets their role refreshed by the export instead of being skipped outright, and
one who has since left the committee keeps the last role we knew them by.

Both columns are nullable with no default, so every row already stored reads
exactly as it did.

Revision ID: 295
Revises: 292
"""
from alembic import op

from app.services.committee_sync_ddl import STATEMENTS

revision = "295"
down_revision = "294"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_marketing_club_contacts_former")
    op.execute("ALTER TABLE marketing_club_contacts DROP COLUMN IF EXISTS former_at")
    op.execute("ALTER TABLE comms_contacts DROP COLUMN IF EXISTS role")
