"""A member row may only ever link to a player of the SAME club.

The Directory, the Accounts list and every other people surface read
``fee_members`` and follow ``player_id`` through to ``players``. Nothing stopped
that link pointing at another club's player, and when the fee derivation started
enrolling opponents (migration 222's era, fixed in ``services/fees.py``) that is
exactly what it did: a High Wycombe player appeared in Applecross's Directory,
carrying High Wycombe's photo, email and phone.

Scoping the reads fixed the symptom. This makes the state unrepresentable: a
composite foreign key on ``(organisation_id, player_id)`` means Postgres itself
refuses a member row that points outside its own club, whatever code is doing
the writing.

Added NOT VALID on purpose. It is enforced for every INSERT and UPDATE from the
moment it lands, so no NEW bad row is possible, while rows an earlier bug
already wrote are tolerated until a club runs
``python -m app.scripts.purge_foreign_members``. Validating a populated table
would otherwise fail outright and block the deploy. Once a database is clean,
``ALTER TABLE fee_members VALIDATE CONSTRAINT fk_fee_members_player_same_org``
turns on the retrospective check too — a background scan that does not block
reads or writes.

Revision ID: 223
Revises: 222
"""
from alembic import op

revision = "223"
down_revision = "222"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # A composite FK needs a matching unique key on the referenced side.
    # (id is already the primary key, so this is redundant as a constraint and
    # cheap as an index — it exists only to give the FK something to point at.)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE players ADD CONSTRAINT uq_players_org_id UNIQUE (organisation_id, id);
        EXCEPTION WHEN duplicate_table OR duplicate_object THEN NULL;
        END $$
    """)
    op.execute("""
        DO $$ BEGIN
            ALTER TABLE fee_members
              ADD CONSTRAINT fk_fee_members_player_same_org
              FOREIGN KEY (organisation_id, player_id)
              REFERENCES players (organisation_id, id)
              ON DELETE SET NULL
              NOT VALID;
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE fee_members DROP CONSTRAINT IF EXISTS fk_fee_members_player_same_org")
    op.execute("ALTER TABLE players DROP CONSTRAINT IF EXISTS uq_players_org_id")
