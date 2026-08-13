"""Wizard club → BetterComms list exports, so a send can be reported per club

The Meta Ads page names the clubs that searched for themselves or picked
themselves in the registration wizard, but there was no way to turn that into
outreach. ``wizard_club_lists`` is the record of which wizard clubs went into
which auto-generated BetterComms list, which is what lets "has this club been
emailed yet" be answered: a campaign carries its audience list id, a recipient
carries its contact, and a contact carries its directory club.

``list_id`` deliberately carries NO foreign key to ``comms_lists``. A super
admin tidying up an old list must not take the club's email history with it,
and the id is still exactly what a sent campaign's ``audience.list_id`` holds,
so the tracking keeps resolving after the list itself is gone. ``list_name``
is stored alongside for the same reason.

Revision ID: 251
Revises: 250
"""
from alembic import op

revision = "251"
down_revision = "250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS wizard_club_lists (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            list_id UUID NOT NULL,
            list_name TEXT,
            club_key TEXT NOT NULL,
            club_name TEXT NOT NULL,
            marketing_club_id UUID REFERENCES marketing_clubs(id) ON DELETE SET NULL,
            contacts_added INTEGER NOT NULL DEFAULT 0,
            created_by UUID REFERENCES users(id) ON DELETE SET NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_wizard_club_lists_list_club UNIQUE (list_id, club_key)
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wizard_club_lists_key "
        "ON wizard_club_lists(club_key)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_wizard_club_lists_club "
        "ON wizard_club_lists(marketing_club_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS wizard_club_lists")
