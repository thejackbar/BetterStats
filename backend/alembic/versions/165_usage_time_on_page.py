"""Usage tracking — time-on-page column

Nothing in `usage_events` ever recorded how long a visitor actually stayed on
a page. `duration_ms` looks like it would answer that but it's backend API
response latency (set by the request middleware), not visitor dwell time —
there is no session/duration concept anywhere in the schema.

Adds `time_on_page_ms` (nullable INTEGER), populated by a new `page_exit`
event fired by the frontend beacon (`usePageView.js`) when a visitor
navigates away, backgrounds the tab, or closes it (`visibilitychange` /
`pagehide`, via `navigator.sendBeacon` for reliability). Session duration
itself isn't a stored value — it's computed on read (`services/usage.py`)
by grouping a visitor's page_view timestamps into 30-minute-gap sessions and
adding the final page's `time_on_page_ms` for the tail.

Revision ID: 165
Revises: 164
Create Date: 2026-07-19
"""
from alembic import op


revision = '165'
down_revision = '164'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE usage_events ADD COLUMN IF NOT EXISTS time_on_page_ms INTEGER")
    # Speeds up matching a session's last page_view to its page_exit row
    # (visitor_id + event_type, ordered by time) in the duration/journey queries.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_usage_events_visitor_type_created "
        "ON usage_events(visitor_id, event_type, created_at) WHERE visitor_id IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_usage_events_visitor_type_created")
    op.execute("ALTER TABLE usage_events DROP COLUMN IF EXISTS time_on_page_ms")
