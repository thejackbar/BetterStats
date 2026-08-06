"""Record WHICH club a Contact-form enquiry named, not just what was typed.

The Contact form's Club name was a free-text box, so an enquiry arrived as a
string a person typed under time pressure - an abbreviation, a misspelling, the
association's name instead of the club's. Everything downstream then had to
match that string back to a real club (``_resolve_onboarding_club`` falls back
to a synthetic ``manual:`` guid keyed on the name), so two spellings of one club
read as two clubs.

The form now searches the Cricket Australia club list, so a picked club arrives
with its real CA organisation guid. ``club_org_id`` holds it; ``club_source``
records how the name was arrived at (``search`` = picked from the list,
``manual`` = typed in, which stays available for clubs outside Australia that
the CA list does not carry).

Both nullable: every enquiry already stored predates the search, and a manual
entry legitimately has no guid.

Revision ID: 224
Revises: 223
"""
from alembic import op

revision = "224"
down_revision = "223"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE club_onboarding_requests "
        "ADD COLUMN IF NOT EXISTS club_org_id TEXT"
    )
    op.execute(
        "ALTER TABLE club_onboarding_requests "
        "ADD COLUMN IF NOT EXISTS club_source TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE club_onboarding_requests DROP COLUMN IF EXISTS club_source")
    op.execute("ALTER TABLE club_onboarding_requests DROP COLUMN IF EXISTS club_org_id")
