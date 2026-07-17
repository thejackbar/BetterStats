"""Pause/cancel control signal for a running sync_runs row.

Adds sync_runs.control (nullable text: NULL | 'pause' | 'cancel'), the
cooperative flag a long-running sync loop polls (services/sync.py's
_check_sync_control) so a Super Admin can Pause/Cancel a Full Sync from the
All Clubs page. status also gains two new values written by the same
feature ('paused', 'cancelled') — status stays an unconstrained Text column
(same as every other status here), so no DDL is needed for that half.

Revision ID: 160
Revises: 159
Create Date: 2026-07-17
"""
from alembic import op


revision = '160'
down_revision = '159'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Idempotent raw DDL (byte-for-byte the main.py lifespan mirror).
    op.execute("ALTER TABLE sync_runs ADD COLUMN IF NOT EXISTS control TEXT")


def downgrade() -> None:
    op.execute("ALTER TABLE sync_runs DROP COLUMN IF EXISTS control")
