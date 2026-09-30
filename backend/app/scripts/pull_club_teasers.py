"""Pull marketing teaser snapshots for clubs that have not registered.

    python -m app.scripts.pull_club_teasers [all|<marketing-club-id>] [--limit N]
        [--sample N] [--apply] [--include-trialists] [--pause SECONDS]
        [--concurrency N] [--type junior=include] [--no-type-filter]

Dry run by default: it lists how many clubs are due and touches nothing. With
``--apply`` it pulls the due clubs, never-pulled first, then clubs with an
emailable contact, then the longest overdue, and honours the operator's Stop
switch between clubs. Safe to run repeatedly and to interrupt: a club is
written when ITS pull finishes, and what is due is decided by each snapshot's
own ``next_pull_at``, so a second run carries on where the first stopped.

Who is eligible follows the Club Directory type filters. By default juniors,
carnivals, schools, rep orgs and Cricket Australia orgs are left out (or
whatever General Settings ``club_teaser_type_modes`` holds). ``--type
key=include|exclude`` (repeatable) overrides that, and ``--no-type-filter``
turns it off.

``--sample N`` is the first live check: N clubs (default 20), one at a time,
with a per-club line showing status and Cricket Australia calls. Dry-run
unless ``--apply`` is also given.

``--apply`` ends with a work report so a small run can be extrapolated: wall
clock, clubs a minute, calls a second, a breakdown by outcome (ok, empty,
junior_only, error) with calls and seconds per club, and a projection for every
club still due, at the batch sizes the scheduled job might use. A dry run counts
what is due and makes no calls, so it has nothing to time.

This is also how the directory is filled the first time (about 20-30 Cricket
Australia calls a club); the daytime job is only the trickle after that.
"""
import argparse
import asyncio
import logging
import time

from app.services import club_directory, club_teaser, club_teaser_report, platform_settings


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", default="all")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--sample", type=int, nargs="?", const=20, default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-trialists", action="store_true")
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--concurrency", type=int, default=2)
    ap.add_argument("--type", action="append", default=[], metavar="KEY=MODE")
    ap.add_argument("--no-type-filter", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    if a.no_type_filter:
        modes = {}
    elif a.type:
        modes = club_teaser.clean_type_modes(
            dict(t.split("=", 1) for t in a.type if "=" in t))
    else:
        from app.models.db import async_session_maker
        async with async_session_maker() as s:
            modes = await platform_settings.get_club_teaser_type_modes(s)
    print(f"type filters: {modes or 'none'}")

    limit, concurrency = a.limit, a.concurrency
    if a.sample is not None:
        limit, concurrency = a.sample, 1

    club_id = None if a.target == "all" else a.target
    from app.models.db import async_session_maker
    async with async_session_maker() as s:
        # Everything still due, not just this run's slice: it is what the
        # projection extrapolates to.
        total_due = len(await club_teaser.due_clubs(
            s, 1_000_000, include_trialists=a.include_trialists, club_id=club_id,
            type_modes=modes))
        configured = await platform_settings.get_club_teaser_nightly_limit(s)
    print(f"clubs due in total: {total_due}")

    started = time.monotonic()
    summary = await club_teaser.run_batch(
        limit, should_stop=club_directory.is_crawl_paused, pause_seconds=a.pause,
        club_concurrency=concurrency, include_trialists=a.include_trialists,
        club_id=club_id, dry_run=not a.apply, type_modes=modes)
    elapsed = time.monotonic() - started
    detail = summary.pop("detail", [])
    for k, v in summary.items():
        print(f"{k:12} {v}")
    if a.sample is not None or not a.apply:
        print()
        for d in detail[: (a.sample or 20)]:
            print(f"  {d['name'][:44]:44} {d.get('state') or '':4} "
                  f"{d.get('status') or '-':12} {d.get('calls', 0):3} calls"
                  + (f" {d['secs']:5.1f}s" if d.get("secs") else "")
                  + (f"  {d['error']}" if d.get("error") else ""))
    if not a.apply:
        print("\nDry run: nothing pulled, so nothing to time. Re-run with --apply.")
    else:
        # Concurrency here is what THIS run used; the projection re-divides by
        # what the scheduled job uses, from per-club latency.
        print(f"(this run: {concurrency} club(s) at a time, {a.pause}s pause after each)")
        for line in club_teaser_report.report_lines(
                detail, elapsed, total_due=max(0, total_due - len(club_teaser_report.done_rows(detail))),
                pause_seconds=a.pause, configured_limit=configured):
            print(line)
    if summary.get("stopped"):
        print("\nStopped by the operator Stop switch before the batch finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
