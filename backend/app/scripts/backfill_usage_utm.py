"""Backfill `usage_events.utm_id` from the stored URL, then report directory match.

The Clubs Directory ties a site visit to a club by matching
`usage_events.utm_id` against `marketing_clubs.utm_code`. A BetterCricket
outreach email tags every link with the club's code as `?utm_id=<utm_code>`,
and the SPA's page-view beacon (`usePageView`) is meant to capture it into the
`utm_id` column.

But the full landing URL is ALSO stored on every page_view, in `path`
(`location.pathname + location.search`) and in `landing_path` (the first URL the
visitor arrived on). So when a click carried `?utm_id=…` but the column ended up
NULL — an early visit before the beacon captured it, a blocked sessionStorage, a
beacon that lost the field — the code is still recoverable straight from the
stored URL. This script pulls it out and fills the column in place.

It is read-only first: it prints a diagnosis (how many page_views carry a utm_id
in the column vs only in the URL, and how many of those codes actually match a
club in the directory) BEFORE writing anything. Pass `dry` to stop after the
diagnosis. Re-runnable (idempotent — only fills NULLs).

Usage from the backend container:
  # report only, change nothing:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_usage_utm dry
  # diagnose then backfill:
  docker exec -e PYTHONPATH=/app betterstats-backend \\
    python -m app.scripts.backfill_usage_utm
"""

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker

# Pull the value of utm_id from a stored URL/query string. POSIX regex; the
# capture group is what substring() returns. Stops at the next param or fragment.
_UTM_ID_RE = r"[?&]utm_id=([^&#]+)"


async def _scalar(session, sql, **params):
    return (await session.scalar(text(sql), params)) or 0


async def diagnose(session) -> dict:
    """Counts that explain whether there's anything to recover, and why the
    directory might read empty."""
    total = await _scalar(
        session, "SELECT COUNT(*) FROM usage_events WHERE event_type = 'page_view'")
    with_col = await _scalar(
        session,
        "SELECT COUNT(*) FROM usage_events "
        "WHERE event_type = 'page_view' AND utm_id IS NOT NULL")
    # Page-views with NO utm_id column but the code IS still in the stored URL.
    recoverable = await _scalar(
        session,
        "SELECT COUNT(*) FROM usage_events "
        "WHERE event_type = 'page_view' AND utm_id IS NULL "
        "AND (path ~ :re OR landing_path ~ :re)",
        re=_UTM_ID_RE)
    # Distinct codes currently in the column that match a directory club, and that
    # do NOT — a non-zero "unmatched" usually means a format/case mismatch.
    matched_codes = await _scalar(
        session,
        "SELECT COUNT(DISTINCT ue.utm_id) FROM usage_events ue "
        "WHERE ue.event_type = 'page_view' AND ue.utm_id IS NOT NULL "
        "AND EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_id)")
    unmatched = (await session.execute(text(
        "SELECT ue.utm_id, COUNT(*) AS n FROM usage_events ue "
        "WHERE ue.event_type = 'page_view' AND ue.utm_id IS NOT NULL "
        "AND NOT EXISTS (SELECT 1 FROM marketing_clubs mc WHERE mc.utm_code = ue.utm_id) "
        "GROUP BY ue.utm_id ORDER BY n DESC LIMIT 20"))).all()
    return {
        "page_views": total,
        "with_utm_id_column": with_col,
        "recoverable_from_url": recoverable,
        "distinct_codes_matching_a_club": matched_codes,
        "unmatched_codes_sample": [(r[0], int(r[1])) for r in unmatched],
    }


async def backfill(session) -> dict:
    """Fill the utm_id column from path, then from landing_path for any still
    NULL. Lowercased to match the lowercase codes the directory stores."""
    res_path = await session.execute(text(
        "UPDATE usage_events "
        "SET utm_id = lower(substring(path from :re)) "
        "WHERE event_type = 'page_view' AND utm_id IS NULL AND path ~ :re"),
        {"re": _UTM_ID_RE})
    res_land = await session.execute(text(
        "UPDATE usage_events "
        "SET utm_id = lower(substring(landing_path from :re)) "
        "WHERE event_type = 'page_view' AND utm_id IS NULL AND landing_path ~ :re"),
        {"re": _UTM_ID_RE})
    await session.commit()
    return {"from_path": res_path.rowcount or 0,
            "from_landing_path": res_land.rowcount or 0}


def _print_diag(label: str, d: dict) -> None:
    print(f"\n── {label} ─────────────────────────────")
    print(f"  page_views (total):                 {d['page_views']}")
    print(f"  with a utm_id column value:         {d['with_utm_id_column']}")
    print(f"  NULL column but code still in URL:  {d['recoverable_from_url']}")
    print(f"  distinct codes matching a club:     {d['distinct_codes_matching_a_club']}")
    if d["unmatched_codes_sample"]:
        print("  codes in column with NO matching club (top 20):")
        for code, n in d["unmatched_codes_sample"]:
            print(f"      {n:>6}  {code}")
    else:
        print("  every code in the column matches a club ✓")


async def main(dry: bool) -> None:
    async with async_session_maker() as session:
        before = await diagnose(session)
        _print_diag("BEFORE", before)

        if dry:
            print("\n(dry run — nothing written. Drop 'dry' to backfill.)")
            return
        if not before["recoverable_from_url"]:
            print("\nNothing to backfill: no page_view has a utm_id in its URL that "
                  "isn't already in the column.")
            if not before["with_utm_id_column"]:
                print("No page_view carries a utm_id at all — most likely no one has "
                      "clicked a UTM-tagged outreach link yet.")
            return

        moved = await backfill(session)
        print(f"\nBackfilled utm_id: {moved['from_path']} from path, "
              f"{moved['from_landing_path']} from landing_path.")

        after = await diagnose(session)
        _print_diag("AFTER", after)
        clubs_now = await _scalar(session,
            "SELECT COUNT(*) FROM marketing_clubs mc WHERE EXISTS ("
            "SELECT 1 FROM usage_events ue WHERE ue.utm_id = mc.utm_code "
            "AND ue.utm_id IS NOT NULL AND ue.event_type = 'page_view')")
        print(f"\nClubs the directory now shows as 'visited': {clubs_now}")


if __name__ == "__main__":
    dry = len(sys.argv) > 1 and sys.argv[1].lower() in ("dry", "--dry-run", "-n")
    asyncio.run(main(dry))
