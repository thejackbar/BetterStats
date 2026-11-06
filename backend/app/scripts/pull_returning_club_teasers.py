"""Re-crawl the teaser snapshots of clubs that were once BetterCricket's and may come back.

    python -m app.scripts.pull_returning_club_teasers [--limit N] [--due-only]
        [--rate CALLS_PER_SECOND] [--concurrency N] [--pause SECONDS]
        [--type KEY=MODE] [--no-type-filter] [--apply]

Which clubs: a directory club whose BetterCricket club is ARCHIVED (a test club,
an abandoned trial, a club that left), or whose trial has EXPIRED and who does
not subscribe. Nobody else: not a club that has never been BetterCricket's, not
a paying club or one on a trial that is still running. The usual rules still
hold: a club marked excluded or not interested, one without a real Cricket
Australia guid, and the Club Directory type filters (juniors, carnivals,
schools, rep teams, governing bodies) leave a club out.

Dry run by default: it says how many clubs are in the group (archived and
lapsed), how many are due right now, and lists the first of them, and it makes
no Cricket Australia call. With ``--apply`` it pulls them, never-pulled first and
then the longest since pulled, and it honours the operator's Stop switch between
clubs. Each club is written when ITS pull finishes, so the run is safe to stop
and to repeat.

By default EVERY club in the group is re-pulled, whether or not it is due (that
is what "re-crawl" means here). ``--due-only`` pulls only those whose snapshot is
missing, overdue or on an old schema. ``--limit N`` takes the first N, for a
sample.

Calls are paced (rule: outbound traffic to Cricket Australia is bounded and
polite). ``--rate`` is calls a second on average; unset, it uses the rate
configured for the always-on crawl, or 1 a second if none is set. The always-on
crawl also pulls these clubs when they are due, on its own pacer, so while it is
running the two add together; use a modest ``--rate`` or run this while the crawl
is idle.
"""
import argparse
import asyncio
import logging
import time

from app.services import club_directory, club_teaser, club_teaser_report, platform_settings
from app.services.call_pacer import CallPacer

DEFAULT_RATE = 1.0


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--limit", type=int, default=0, help="the first N clubs (default: all)")
    ap.add_argument("--due-only", action="store_true", help="only clubs whose snapshot is missing, overdue or old")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--rate", type=float, default=None, metavar="CALLS_PER_SECOND")
    ap.add_argument("--type", action="append", default=[], metavar="KEY=MODE")
    ap.add_argument("--no-type-filter", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if a.limit < 0 or a.concurrency < 1:
        ap.error("--limit must be 0 or more and --concurrency 1 or more")

    from app.models.db import async_session_maker
    if a.no_type_filter:
        modes = {}
    elif a.type:
        modes = club_teaser.clean_type_modes(dict(t.split("=", 1) for t in a.type if "=" in t))
    else:
        async with async_session_maker() as s:
            modes = await platform_settings.get_club_teaser_type_modes(s)
    print(f"type filters: {modes or 'none'}")

    async with async_session_maker() as s:
        group = await club_teaser.due_clubs(s, 1_000_000, returning_only=True, force=True, type_modes=modes)
        due = await club_teaser.due_clubs(s, 1_000_000, returning_only=True, type_modes=modes)
        configured = await platform_settings.get_club_teaser_rate(s)
        w_start, w_end = await platform_settings.get_club_teaser_window(s)
    archived = sum(1 for c in group if c.get("why") == "archived")
    print(f"clubs in the group: {len(group)} ({archived} archived, {len(group) - archived} with an expired trial and no subscription)")
    print(f"due right now: {len(due)}")

    rate = a.rate if a.rate is not None else (configured or DEFAULT_RATE)
    if not 0 < rate <= platform_settings.TEASER_MAX_RATE:
        ap.error(f"--rate must be above 0 and at most {platform_settings.TEASER_MAX_RATE:g}")
    limit = a.limit or 1_000_000

    if not a.apply:
        chosen = (due if a.due_only else group)
        chosen = chosen[:a.limit] if a.limit else chosen
        print(f"\nDry run: {len(chosen)} club(s) would be pulled at about {rate:g} calls a second. "
              f"Nothing was pulled. Add --apply to pull them.")
        for c in chosen[:25]:
            print(f"  {c['name'][:48]:48} {c.get('why') or '':9} {c.get('state') or ''}")
        if len(chosen) > 25:
            print(f"  ... and {len(chosen) - 25} more")
        return 0

    pacer = CallPacer(rate)
    started = time.monotonic()
    summary = await club_teaser.run_batch(
        limit, should_stop=club_directory.is_crawl_paused, pause_seconds=a.pause,
        club_concurrency=a.concurrency, type_modes=modes, returning_only=True, force=not a.due_only,
        api_factory=lambda: club_teaser.LiveAPI(pacer=pacer))
    elapsed = time.monotonic() - started
    detail = summary.pop("detail", [])
    for k, v in summary.items():
        print(f"{k:12} {v}")
    print(f"(paced at {rate:g} calls/s on average, {a.concurrency} club(s) at a time, {elapsed / 60:.1f} minutes)")
    for line in club_teaser_report.report_lines(
            detail, elapsed, total_due=0, rate=rate, window_hours=float(w_end - w_start),
            window_label=f"{w_start:02d}:00-{w_end % 24:02d}:00 Perth"):
        print(line)
    if summary.get("stopped"):
        print("\nStopped by the operator Stop switch before the run finished. Run it again to carry on.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
