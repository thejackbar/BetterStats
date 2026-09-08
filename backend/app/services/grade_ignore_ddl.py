"""The ONE copy of the dismissed-grade-pair DDL.

Alembic (migration 291) and `main.py`'s lifespan mirror both run this list, in
this order, per the `vote_medal_ddl` rule — two copies is how the two drift.
Every statement is idempotent, because the lifespan re-runs the whole list on
every boot.
"""

STATEMENTS: list[str] = [
    """
    CREATE TABLE IF NOT EXISTS grade_merge_pair_ignores (
        id SERIAL PRIMARY KEY,
        org_id UUID NOT NULL,
        name_a TEXT NOT NULL,
        name_b TEXT NOT NULL,
        created_at TIMESTAMPTZ DEFAULT NOW(),
        UNIQUE (org_id, name_a, name_b)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_grade_merge_pair_ignores_org
        ON grade_merge_pair_ignores (org_id)
    """,
]
