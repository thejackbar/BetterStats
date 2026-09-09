"""Migration 298 — the crawl re-reads an existing club's associations.

ONE copy of the DDL, run by alembic's 298 AND by the lifespan mirror in
``main.py``, per the ``vote_medal_ddl`` rule: two copies is how the two start
disagreeing about the schema. Every statement is idempotent, because the
lifespan re-runs the whole list on every boot.

``marketing_clubs.associations_fetched_at``
    When ``enrich_associations`` last SUCCEEDED for this club. It exists
    because ``last_crawled_at`` cannot answer the question: ``_upsert_club``
    bumps that on every discovery pass, so it says when the club was last
    SEEN, never when its associations were last READ.

    Without it the enrichment frontier is ``associations IS NULL`` and nothing
    else, so a club's associations are fetched exactly once and then frozen
    for the life of the row — a club that changes association keeps the old
    one for ever, and nothing on any screen says so.

Deliberately NO index. The frontier query orders by ``last_crawled_at``, not
by this column, so an index here could not serve the sort — and the whole
table is around 6,900 rows, where the scan is not worth an index to maintain.

The backfill stamps a club that ALREADY has associations with the best
evidence available of when we last had them (``last_crawled_at``, else
``first_seen_at``). It is guarded on the stamp still being NULL, so a re-run
writes nothing and a club enriched since the migration keeps its real value.
Stamping rather than leaving NULL is what stops the whole directory becoming
refresh-due in one burst on the day this ships: the oldest-crawled clubs come
due first, and the rest drain in ``marketing_crawl_nightly_limit`` batches at
the crawler's own pace.

A club whose associations have never been fetched is left NULL, which is
correct — it is still on the ordinary backfill frontier, and that frontier is
what ``run_continuous`` reads to decide the backfill is finished.
"""
from __future__ import annotations

STATEMENTS: list[str] = [
    "ALTER TABLE marketing_clubs "
    "ADD COLUMN IF NOT EXISTS associations_fetched_at TIMESTAMPTZ",
    "UPDATE marketing_clubs "
    "SET associations_fetched_at = COALESCE(last_crawled_at, first_seen_at) "
    "WHERE associations IS NOT NULL AND associations_fetched_at IS NULL",
]
