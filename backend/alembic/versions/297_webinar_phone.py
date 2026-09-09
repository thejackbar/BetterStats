"""A phone number on a webinar registration

Asked for directly, after the page shipped: gather the phone number too.

A registration is a lead somebody follows up, and an email address alone is a
weak way to reach a club officer. It also improves the Meta match quality on
the conversion we already send — `meta_capi.send_complete_registration_event`
has always accepted a hashed phone and has never had one to hash.

Re-runs the whole of `webinar_ddl.STATEMENTS` rather than issuing a lone ALTER:
every statement in that list is idempotent, so a database at 296 picks up the
added column and a database that has never had the table gets it created with
the column already on it. One list, one place to change, no second copy of the
column definition to drift.

Revision ID: 297
Revises: 296
"""
from alembic import op

from app.services.webinar_ddl import STATEMENTS

revision = "297"
down_revision = "296"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for statement in STATEMENTS:
        op.execute(statement)


def downgrade() -> None:
    # Deliberately narrow: 296 owns the table, so undoing THIS migration drops
    # only what it added. Dropping the table here would destroy every
    # registration on a downgrade that was only ever about one column.
    op.execute("ALTER TABLE webinar_registrations DROP COLUMN IF EXISTS phone")
