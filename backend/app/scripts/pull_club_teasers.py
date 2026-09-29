"""Pull marketing teaser snapshots for clubs that have not registered.

    python -m app.scripts.pull_club_teasers [all|<marketing-club-id>] [--limit N]
        [--apply] [--include-trialists] [--pause SECONDS] [--concurrency N]

Dry run by default: it lists how many clubs are due and touches nothing. With
``--apply`` it pulls the due clubs, never-pulled first, then clubs with an
emailable contact, then the longest overdue, and honours the operator's Stop
switch between clubs. Safe to run repeatedly and to interrupt: a club is
written when ITS pull finishes, and what is due is decided by each snapshot's
own ``next_pull_at``, so a second run carries on where the first stopped.

This is also how the directory is filled the first time (about 20-30 Cricket
Australia calls a club); the nightly job is only the trickle after that.
"""
import argparse
import asyncio
import logging

from app.services import club_directory, club_teaser


async def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("target", nargs="?", default="all")
    ap.add_argument("--limit", type=int, default=100)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--include-trialists", action="store_true")
    ap.add_argument("--pause", type=float, default=0.5)
    ap.add_argument("--concurrency", type=int, default=2)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    summary = await club_teaser.run_batch(
        a.limit, should_stop=club_directory.is_crawl_paused, pause_seconds=a.pause,
        club_concurrency=a.concurrency, include_trialists=a.include_trialists,
        club_id=None if a.target == "all" else a.target, dry_run=not a.apply)
    for k, v in summary.items():
        print(f"{k:12} {v}")
    if not a.apply:
        print("\nDry run: nothing pulled. Re-run with --apply.")
    if summary.get("calls") and summary.get("ok"):
        print(f"\n~{summary['calls'] / max(1, summary['ok'] + summary['empty'] + summary['junior_only'] + summary['error']):.0f} calls per club")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
