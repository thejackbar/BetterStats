"""Find each club's crest and store its season-page look (accent colour, light or dark).

    python -m app.scripts.backfill_club_teaser_themes [--limit N] [--rate PER_SECOND]
        [--club TEXT] [--redo] [--ignore-stop] [--apply]

New pulls do this by themselves (the crawl's name search already returns the
crest). This is for the clubs already pulled. A club is due when it has a good
snapshot, is not a live customer, and has no crest address on its directory row
or no theme yet or its logo address has changed (``--redo`` reads every club
with a crest again, for after a change to the colour rules).

Dry run by default: says how many clubs are due and lists the first of them,
fetching nothing. ``--apply`` makes, per club, one Cricket Australia name search
when the club has no crest address yet (the same search the crawl and /trial
use, to find it) and one GET for the logo image, each paced at ``--rate`` a
second (default 2, at most 10). It writes the crest address on the directory
row (only where that is empty) and the ``theme`` column: the snapshot is
untouched, so no picture is marked out of date. It honours the operator's Stop switch between
clubs; ``--ignore-stop`` runs anyway and leaves the switch alone, as
``pull_returning_club_teasers`` does. Each club is written as it is read, so a
run is safe to stop and to repeat.
"""
from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy import text

from app.services import club_directory, club_teaser_theme as tt
from app.services.call_pacer import CallPacer
from app.services.club_teaser_link import NOT_A_CUSTOMER_SQL

DEFAULT_RATE = 2.0
MAX_RATE = 10.0
CALL_TIMEOUT = 30.0     # a search or a logo download that takes longer is given up on, so one hung request cannot freeze a run
PROGRESS_EVERY = 25     # clubs between progress lines


def _say(message: str) -> None:
    print(message, flush=True)   # flushed: redirected to a file, Python would otherwise hold it back until the end


async def due(session, *, limit: int = 0, club: str = "", redo: bool = False) -> list:
    where = "t.status = 'ok' AND t.snapshot IS NOT NULL AND " + NOT_A_CUSTOMER_SQL
    if redo:
        where += " AND NULLIF(btrim(mc.logo_url), '') IS NOT NULL"
    else:
        where += (" AND (NULLIF(btrim(mc.logo_url), '') IS NULL OR t.theme IS NULL"
                  " OR t.theme->>'src' IS DISTINCT FROM mc.logo_url"
                  " OR (t.theme->>'v')::int IS DISTINCT FROM :v)")
    params: dict = {"v": tt.THEME_VERSION}
    if club:
        where += " AND mc.name ILIKE :n"
        params["n"] = f"%{club}%"
    sql = ("SELECT mc.id AS club_id, mc.name, mc.logo_url, mc.grassroots_guid AS guid FROM club_teaser_snapshots t "
           "JOIN marketing_clubs mc ON mc.id = t.marketing_club_id WHERE " + where +
           " ORDER BY (t.theme IS NULL) DESC, mc.name")
    if limit:
        sql += " LIMIT :lim"
        params["lim"] = limit
    return [dict(r) for r in (await session.execute(text(sql), params)).mappings().all()]


async def run(session_maker, *, limit=0, club="", redo=False, apply=False, rate=DEFAULT_RATE,
              ignore_stop=False, fetch=tt.fetch_logo, finder=tt.find_logo, pacer=None, out=_say) -> dict:
    async with session_maker() as s:
        clubs = await due(s, limit=limit, club=club, redo=redo)
    summary = {"due": len(clubs), "read": 0, "no_accent": 0, "unreadable": 0, "no_logo": 0,
               "found": 0, "stopped": False}
    if not apply:
        out(f"{len(clubs)} club(s) due. Dry run: nothing fetched. Add --apply to read their logos.")
        for c in clubs[:25]:
            out(f"  {c['name']}  {c['logo_url'] or '(no crest address yet: will be searched for)'}")
        if len(clubs) > 25:
            out(f"  ... and {len(clubs) - 25} more")
        return summary
    pacer = pacer or CallPacer(rate)

    async def bounded(coro):
        try:
            return await asyncio.wait_for(coro, CALL_TIMEOUT)
        except asyncio.TimeoutError:
            return None

    async def fetch_bounded(url):
        return await bounded(fetch(url))

    for n, c in enumerate(clubs, 1):
        if n > 1 and (n - 1) % PROGRESS_EVERY == 0:
            out(f"  {n - 1}/{len(clubs)} clubs done: {summary['read']} read, "
                f"{summary['found']} crests found, {summary['no_logo']} with none, {summary['unreadable']} unreadable")
        if not ignore_stop:
            async with session_maker() as s:
                if await club_directory.is_crawl_paused(s):
                    summary["stopped"] = True
                    break
        logo = (c["logo_url"] or "").strip()
        if not logo:
            await pacer.wait()
            logo = await bounded(finder(c["name"], c["guid"]))
            if not logo:
                summary["no_logo"] += 1
                continue
            summary["found"] += 1
            async with session_maker() as s:
                await tt.remember_logo(s, c["club_id"], logo)
        await pacer.wait()
        async with session_maker() as s:
            theme = await tt.store_theme(s, c["club_id"], logo, fetch=fetch_bounded, force=True)
        if theme is None:
            summary["unreadable"] += 1
        else:
            summary["read"] += 1
            if not theme.get("accent"):
                summary["no_accent"] += 1
    out(f"found {summary['found']} crest address(es) ({summary['no_logo']} clubs have none), "
        f"read {summary['read']} logo(s) ({summary['no_accent']} with no colour to use), "
        f"{summary['unreadable']} could not be read, of {summary['due']} due")
    if summary["stopped"]:
        out("Stopped by the operator Stop switch. Run it again to carry on.")
    return summary


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--club", default="", metavar="TEXT")
    ap.add_argument("--redo", action="store_true")
    ap.add_argument("--rate", type=float, default=DEFAULT_RATE, metavar="PER_SECOND")
    ap.add_argument("--ignore-stop", action="store_true")
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args(argv)
    if a.limit < 0 or not 0 < a.rate <= MAX_RATE:
        ap.error(f"--limit must be 0 or more and --rate above 0 and at most {MAX_RATE:g}")
    from app.models.db import async_session_maker
    if a.apply and a.ignore_stop:
        async with async_session_maker() as s:
            if await club_directory.is_crawl_paused(s):
                print("The Stop switch is ON. Ignoring it because --ignore-stop was given; the switch is not changed.")
    await run(async_session_maker, limit=a.limit, club=a.club, redo=a.redo, apply=a.apply,
              rate=a.rate, ignore_stop=a.ignore_stop)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
