"""Club page password protection ("Draft" mode) + trial-ended unpause requests.

A third public-page state alongside is_active's Active/Inactive: the page
exists and is reachable but gated behind a 4-digit PIN, shareable internally
(club admin's own choice) or to gate a lapsed trial as a sales-conversion tool
(Super Admin only). Independent of is_active by design — see
services/club_lock.py and routers/clubs.py.

club_unpause_requests is the queue behind the "email me for access" form shown
only on a trial_ended-gated page, reviewed by Super Admin at
/admin/super/unpause-requests.

Revision ID: 205
Revises: 204
Create Date: 2026-08-02
"""
from alembic import op

revision = "205"
down_revision = "204"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "password_protected BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "password_protect_reason TEXT"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "access_pin_hash TEXT"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "password_protected_at TIMESTAMPTZ"
    )
    op.execute(
        "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS "
        "password_protected_by UUID REFERENCES users(id)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS club_unpause_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
            email TEXT NOT NULL,
            message TEXT,
            status TEXT NOT NULL DEFAULT 'pending',
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            actioned_at TIMESTAMPTZ,
            actioned_by UUID REFERENCES users(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_unpause_requests_org "
        "ON club_unpause_requests(organisation_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_club_unpause_requests_status_created "
        "ON club_unpause_requests(status, created_at DESC)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS club_unpause_requests")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS password_protected_by")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS password_protected_at")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS access_pin_hash")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS password_protect_reason")
    op.execute("ALTER TABLE organisations DROP COLUMN IF EXISTS password_protected")
