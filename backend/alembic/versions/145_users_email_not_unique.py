"""Drop the UNIQUE constraint on users.email.

Club-user email/mobile are now format-validated only, not required to be
unique (routers/club_admin.py's create_club_user / update_club_user no
longer 409 on a duplicate email) — a duplicate insert/update would otherwise
still hit this DB-level constraint and 500 instead of just succeeding.
mobile_number never had a uniqueness constraint, so nothing to do there.
Username is unrelated and stays unique (it's the login credential).

Looks the constraint up by column rather than assuming a fixed name (this
table predates Alembic and its default UNIQUE constraint name was never
pinned down in a migration), so this works regardless of how it was named
when the table was first created.

Revision ID: 145
Revises: 144
Create Date: 2026-07-14
"""
from alembic import op


revision = '145'
down_revision = '144'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        DECLARE
            con record;
        BEGIN
            FOR con IN
                SELECT conname FROM pg_constraint
                WHERE conrelid = 'users'::regclass
                  AND contype = 'u'
                  AND conkey = (
                      SELECT array_agg(attnum) FROM pg_attribute
                      WHERE attrelid = 'users'::regclass AND attname = 'email'
                  )
            LOOP
                EXECUTE format('ALTER TABLE users DROP CONSTRAINT %I', con.conname);
            END LOOP;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE users ADD CONSTRAINT users_email_key UNIQUE (email)")
