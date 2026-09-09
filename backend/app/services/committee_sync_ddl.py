"""Migration 293 — the schema behind a committee Rediscover.

ONE copy of the DDL, run by alembic's 293 AND by the lifespan mirror in
``main.py``, per the ``vote_medal_ddl`` rule: two copies is how the two start
disagreeing about the schema. Every statement is idempotent, because the
lifespan re-runs the whole list on every boot.

Two columns, for the two halves of "make the Directory match PlayHQ":

``marketing_club_contacts.former_at``
    When a Rediscover last found this contact ABSENT from what PlayHQ
    publishes for their club. NULL = currently listed. A Rediscover DELETES a
    delisted officer outright where that is safe, and keeps the row marked
    ``former_at`` where deleting would lose something a person decided — an
    unsubscribe, a bounce, a do-not-contact, a note, a CRM link, or a contact
    somebody added by hand. Deleting an unsubscribed officer would be the
    worst of those: the next crawl would re-add them subscribed and ticked,
    and we would email somebody who opted out. Cleared if they turn up again.

``comms_contacts.role``
    The officer's role at the moment it was last exported or refreshed —
    "President", "Secretary" — so a role change in the Directory reaches
    BetterComms, and so a list can be built from it ("email every Treasurer").
    Deliberately a stored copy rather than a join back to the Directory: an
    officer who has since left keeps the last role we knew them by, which is
    the whole point of leaving them in BetterComms after the Directory prunes
    them.
"""
from __future__ import annotations

STATEMENTS: list[str] = [
    # A delisted officer we could not safely delete. NULL = on PlayHQ today.
    "ALTER TABLE marketing_club_contacts "
    "ADD COLUMN IF NOT EXISTS former_at TIMESTAMPTZ",
    # Partial: the interesting rows are the handful that are no longer listed,
    # not the hundreds of thousands that are.
    "CREATE INDEX IF NOT EXISTS ix_marketing_club_contacts_former "
    "ON marketing_club_contacts(former_at) WHERE former_at IS NOT NULL",
    # Last known role, carried onto the BetterComms contact.
    "ALTER TABLE comms_contacts ADD COLUMN IF NOT EXISTS role TEXT",
]
