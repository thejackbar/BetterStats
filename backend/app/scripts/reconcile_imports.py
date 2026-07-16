"""Re-run BetterImport reconciliation for an org (or every org) on demand.

`reconcile_imported_totals` (services/import_reconcile.py) is idempotent and
self-healing — it wipes and recomputes an org's `import_effective_deltas` from
its `imported_stats` truth rows and current GR coverage, and already runs
automatically as the final pass of every org sync. This script exists so a
fix to the reconciler itself (e.g. migration 152's grade-scoped reconciliation)
can be applied to an org's already-committed import batches immediately,
without waiting for that club's next sync.

Nothing here is destructive to `imported_stats` (the club's uploaded truth) —
only the derived `import_effective_deltas` rows are rebuilt, exactly as a
sync's own reconcile pass would.

Usage from the backend container:
  # one club:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.reconcile_imports <org_id>
  # every club with at least one import (no arg, or "all"):
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.reconcile_imports all
"""

import asyncio
import sys

from sqlalchemy import text as sql_text

from app.models.db import async_session_maker
from app.services.import_reconcile import reconcile_imported_totals


async def reconcile_one(org_id_str: str) -> None:
    written = await reconcile_imported_totals(org_id_str)
    print(f"org {org_id_str}: {written} delta row(s) written")


async def reconcile_all() -> None:
    """Every org that has ever imported anything — a no-import org is a no-op
    inside reconcile_imported_totals anyway, but skipping them here keeps the
    run fast and the output relevant."""
    async with async_session_maker() as session:
        rows = await session.execute(
            sql_text(
                "SELECT DISTINCT o.id, o.name FROM organisations o "
                "JOIN imported_stats ist ON ist.organisation_id = o.id "
                "ORDER BY o.name"
            )
        )
        orgs = [(r[0], r[1]) for r in rows.all()]
    print(f"Reconciling {len(orgs)} organisation(s) with import data...\n")
    failed: list[str] = []
    for idx, (oid, name) in enumerate(orgs, start=1):
        print(f"=== [{idx}/{len(orgs)}] {name} ({oid}) ===")
        try:
            await reconcile_one(str(oid))
        except Exception as exc:
            failed.append(f"{name} ({oid}): {exc}")
            print(f"  !! org failed: {exc}")
    print(f"\nAll organisations done. {len(failed)} failed.")
    for f in failed:
        print(f"  - {f}")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else "all"
    if arg.lower() == "all":
        asyncio.run(reconcile_all())
    else:
        asyncio.run(reconcile_one(arg))
