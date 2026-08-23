"""One-time backfill of usage_events.resolved_marketing_club_id.

WHY
    twenty_sync._engagement's web query normally resolves each event to a club
    with the 7-subquery _RESOLVED_CID expression. That's correct but slow to run
    per club (a full table re-resolution ~6s each), which is why firing a
    single-club recompute on every live signal used to be unsafe. The
    resolved_marketing_club_id column (added in main.py's lifespan) stores that
    resolution once, so a single-club recompute becomes an indexed equality
    (fast_web path). NEW rows are stamped live by crm.check_web_signal_promotion;
    this script fills the EXISTING rows in the scoring window so the fast path is
    correct immediately rather than only for traffic that arrives after deploy.

WHAT
    For rows created within the window (default 90 days — the score's longest
    decay bucket) whose column is still NULL, set it to the SAME _RESOLVED_CID
    the bulk score query computes. Batched by id with a per-batch commit so it
    never takes a long lock or a giant transaction (the exact thing that wedged
    the table before). Idempotent and resumable: it only touches NULL rows, so a
    re-run just continues.

USAGE (inside the backend container)
    python -m app.scripts.backfill_resolved_club                 # last 90 days
    python -m app.scripts.backfill_resolved_club --days 120      # wider window
    python -m app.scripts.backfill_resolved_club --batch 20000   # bigger batches
"""
from __future__ import annotations

import argparse
import asyncio

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services.club_directory import _RESOLVED_CID


async def run(days: int, batch: int) -> None:
    async with async_session_maker() as session:
        bounds = (await session.execute(text(
            "SELECT MIN(id), MAX(id) FROM usage_events "
            "WHERE created_at > NOW() - make_interval(days => :d)"
        ), {"d": days})).first()
        lo, hi = (bounds[0], bounds[1]) if bounds else (None, None)
        if lo is None:
            print("No usage_events in the window — nothing to backfill.")
            return
        print(f"Backfilling resolved_marketing_club_id for id {lo}..{hi} "
              f"(last {days} days), batch {batch} ...")

        total = 0
        start = lo
        while start <= hi:
            end = start + batch - 1
            res = await session.execute(text(f"""
                UPDATE usage_events ue
                SET resolved_marketing_club_id = ({_RESOLVED_CID})::uuid
                WHERE ue.id BETWEEN :lo AND :hi
                  AND ue.created_at > NOW() - make_interval(days => :d)
                  AND ue.resolved_marketing_club_id IS NULL
            """), {"lo": start, "hi": end, "d": days})
            await session.commit()
            total += res.rowcount or 0
            print(f"  ... id {start}..{end}  (updated so far: {total})")
            start = end + 1

        print(f"\nDone. Stamped {total} row(s).")


def main() -> None:
    ap = argparse.ArgumentParser(description="Backfill usage_events.resolved_marketing_club_id.")
    ap.add_argument("--days", type=int, default=90,
                    help="how far back to backfill (default 90. The scoring window)")
    ap.add_argument("--batch", type=int, default=10000,
                    help="rows (by id range) per committed batch (default 10000)")
    args = ap.parse_args()
    asyncio.run(run(args.days, args.batch))


if __name__ == "__main__":
    main()
