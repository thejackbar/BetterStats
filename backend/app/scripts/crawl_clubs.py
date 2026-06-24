"""Crawl the CA/grassroots org graph into the marketing club directory.

Resumable: each run details the next slice of frontier clubs (rows whose
org-detail hasn't been fetched yet) and enqueues their affiliations. Re-run until
``frontier_remaining`` reaches 0. The nightly scheduler job calls the same
``crawl_batch`` with a small cap, so this script is mainly for an operator who
wants to drive it by hand or run a larger one-off batch.

Usage (from the backend container):
  python -m app.scripts.crawl_clubs            # one batch of the configured nightly limit
  python -m app.scripts.crawl_clubs 1000       # detail up to 1000 frontier clubs
  python -m app.scripts.crawl_clubs --stats    # print directory counts, crawl nothing
  python -m app.scripts.crawl_clubs --csv > clubs.csv   # export the directory as CSV

Politeness (concurrency, inter-request delay) is governed by the marketing_crawl_*
settings; this script honours them. Run it off-peak.
"""
import asyncio
import sys

from app.models.db import async_session_maker
from app.services import club_directory as cd


async def _run(limit, stats_only, csv_out):
    async with async_session_maker() as session:
        if stats_only:
            print(await cd.directory_stats(session))
            return
        if csv_out:
            sys.stdout.write(await cd.clubs_to_csv(session))
            return
        before = await cd.directory_stats(session)
        print(f"before: {before}")
        result = await cd.crawl_batch(session, limit=limit)
        print(f"batch:  {result}")
        print(f"after:  {await cd.directory_stats(session)}")


def main(argv):
    limit = None
    stats_only = "--stats" in argv
    csv_out = "--csv" in argv
    for a in argv:
        if a.isdigit():
            limit = int(a)
    asyncio.run(_run(limit, stats_only, csv_out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
