"""Paid vs volunteer work, hours against a shift, and a club's own diary year.

Three unrelated gaps that all needed a column.

**Paid vs volunteer.** ``club_role_types.category`` has accepted ``'paid'``
since the roles catalogue was built, but nothing ever read it, so a club could
not tell the bar manager it employs from the parent who runs the canteen for
nothing. Rather than a second flag that could disagree with the role type, the
distinction stays derived from the role, and the two columns here record what
the derivation decided AT THE TIME the hours were logged. A role retyped later
must not silently rewrite last season's wage bill.

**Diary year.** The Club Diary hard-coded a July start. Northern-hemisphere
clubs, and plenty of southern ones running Jan-Dec administratively, need their
own.

Revision ID: 221
Revises: 220
"""
from alembic import op

revision = "221"
down_revision = "220"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Whether this was paid work, decided from the role's type when logged.
    op.execute("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS is_paid BOOLEAN NOT NULL DEFAULT FALSE")
    # The shift these hours came from, when they came from one. Deliberately no
    # FK: roster_shifts is one of the raw-SQL tables created by the lifespan
    # rather than an ORM model, and an ORM-side constraint against it would make
    # create_all() order-dependent on a fresh database.
    op.execute("ALTER TABLE volunteer_hours ADD COLUMN IF NOT EXISTS roster_shift_id UUID")
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_volunteer_hours_shift
        ON volunteer_hours(roster_shift_id) WHERE roster_shift_id IS NOT NULL
    """)

    # 1-12. July is the existing behaviour, so no club changes by upgrading.
    op.execute("""
        ALTER TABLE organisations
        ADD COLUMN IF NOT EXISTS diary_start_month INTEGER NOT NULL DEFAULT 7
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS diary_start_month")
    op.execute("DROP INDEX IF EXISTS ix_volunteer_hours_shift")
    for col in ("is_paid", "roster_shift_id"):
        op.execute(f"ALTER TABLE volunteer_hours DROP COLUMN IF EXISTS {col}")
