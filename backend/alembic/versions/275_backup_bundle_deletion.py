"""Record when a backup bundle's files were deleted, and by whom

A backup task row has always outlived the bundle it wrote: retention pruning
removes the directory on disk and the row keeps pointing at a path that is no
longer there, with nothing to say so. That was survivable while deletion only
ever happened on a timer; now a super admin can select old bundles and delete
them from the Backup settings page, so the task list has to be able to say
"the files for this run are gone" rather than offering a download and a
restore that cannot work.

Two nullable columns, no backfill: a row with NULL here means the bundle is
still expected on disk, which is exactly what every existing row meant
before this. ``deleted_reason`` separates a super admin's own deletion from
routine retention pruning, since only one of those is worth asking about.

Revision ID: 275
Revises: 274
Create Date: 2026-08-21
"""
from alembic import op


revision = '275'
down_revision = '274'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS bundle_deleted_at TIMESTAMPTZ")
    op.execute(
        "ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS bundle_deleted_by UUID "
        "REFERENCES users(id) ON DELETE SET NULL"
    )
    op.execute("ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS bundle_deleted_reason TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE backup_tasks DROP COLUMN IF EXISTS bundle_deleted_reason")
    op.execute("ALTER TABLE backup_tasks DROP COLUMN IF EXISTS bundle_deleted_by")
    op.execute("ALTER TABLE backup_tasks DROP COLUMN IF EXISTS bundle_deleted_at")
