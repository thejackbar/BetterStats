"""Login attempt audit log

Adds ``login_attempts`` — one append-only row per login attempt (success or
failure) so we can see who is trying to sign in, from where, and with which
username/email.

Stored per attempt: the attempted ``username`` (lowercased, as submitted), the
``success`` flag + a ``failure_reason`` when it failed, the resolved
``user_id``/``org_id`` when the username matched a real account, a truncated
SHA-256 ``ip_hash`` (never the raw IP — same treatment as ``usage_events``), the
``user_agent`` and Cloudflare ``country``. The password is never stored.

Mirrored idempotently in main.py lifespan so the API boots even if alembic
hasn't run yet.

Revision ID: 124
Revises: 123
Create Date: 2026-07-01
"""
from alembic import op


revision = '124'
down_revision = '123'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS login_attempts (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            username TEXT NOT NULL,
            success BOOLEAN NOT NULL DEFAULT false,
            failure_reason TEXT,
            user_id UUID,
            org_id UUID,
            ip_hash TEXT,
            user_agent TEXT,
            country TEXT
        )
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_created "
        "ON login_attempts(created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_username_created "
        "ON login_attempts(username, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_ip_created "
        "ON login_attempts(ip_hash, created_at DESC) WHERE ip_hash IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_login_attempts_failures "
        "ON login_attempts(created_at DESC) WHERE success = false"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS login_attempts")
