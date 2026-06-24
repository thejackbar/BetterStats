"""Crawl the PlayHQ public directory into the marketing club directory.

Two phases (see ``app.services.club_directory``): discovery pages the PlayHQ
search to enumerate every AU club + committee (first run, or with --rediscover);
association enrichment then walks the frontier (clubs whose associations aren't
fetched yet), so the run is resumable — re-run until ``associations_pending``
reaches 0. The nightly scheduler job calls the same ``crawl_batch`` with a small
cap, so this script is mainly for an operator driving it by hand.

Usage (from the backend container):
  python -m app.scripts.crawl_clubs              # one batch (discovers on first run)
  python -m app.scripts.crawl_clubs 1000         # enrich up to 1000 frontier clubs
  python -m app.scripts.crawl_clubs --rediscover # re-page the club list, then enrich
  python -m app.scripts.crawl_clubs --stats      # print directory counts, crawl nothing
  python -m app.scripts.crawl_clubs --csv > clubs.csv   # export the directory as CSV

Politeness (concurrency, inter-request delay) is governed by the marketing_crawl_*
settings; this script honours them. Run it off-peak.
"""
import asyncio
import sys

from app.models.db import async_session_maker
from app.services import club_directory as cd


async def _run(limit, stats_only, csv_out, rediscover):
    async with async_session_maker() as session:
        if stats_only:
            print(await cd.directory_stats(session))
            return
        if csv_out:
            sys.stdout.write(await cd.clubs_to_csv(session))
            return
        before = await cd.directory_stats(session)
        print(f"before: {before}")
        result = await cd.crawl_batch(session, limit=limit, rediscover=rediscover)
        print(f"batch:  {result}")
        print(f"after:  {await cd.directory_stats(session)}")


def main(argv):
    limit = None
    stats_only = "--stats" in argv
    csv_out = "--csv" in argv
    rediscover = "--rediscover" in argv
    for a in argv:
        if a.isdigit():
            limit = int(a)
    asyncio.run(_run(limit, stats_only, csv_out, rediscover))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
