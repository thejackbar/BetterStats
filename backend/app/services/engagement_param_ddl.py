"""The DDL for ``engagement_parameter_revisions`` (migration 270), in ONE list
that both alembic and ``main.py``'s lifespan run, in the same order, so the two
copies cannot drift.

Every statement is idempotent, because the lifespan re-runs the whole list on
every boot. Same arrangement as services/vote_medal_ddl.py.
"""
from __future__ import annotations

ENGAGEMENT_PARAM_STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS engagement_parameter_revisions (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        values_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        overrides_json JSONB NOT NULL DEFAULT '{}'::jsonb,
        changed_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
        note TEXT,
        recalc_summary JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS ix_engagement_param_revisions_created
    ON engagement_parameter_revisions(created_at DESC)
    """,
]
