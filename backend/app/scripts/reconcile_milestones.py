"""Bring a club's stored career milestones into line with its players' figures.

WHY
---
Until v9.91.1 the stored milestones only ever grew, and were worked out from a
different total from the one the player's profile shows. For a day in
September 2026 the effective view double-counted Shoalwater Bay's imported
seasons, and the milestones minted then are still there: "500 wickets" for a
bowler on 478, "9,000 runs" for a batter on 8,453.

WHAT IT DOES
------------
Runs the same writer a sync now runs (``sync._compute_milestones`` with
``reconcile=True``): a threshold counts as reached when either the figure the
player's profile opens on (``milestone_totals.profile_totals``) or their whole
career across every grade reaches it. One they reach and have no row for is
added; a stored one that neither figure reaches is removed. (Measuring the
profile's figure alone proposed removing 352 of Shoalwater Bay's milestones,
most of them reached with junior matches or on Cricket Australia's own total.) A
threshold still reached keeps its original date.

A milestone row is derived output — the writer is the only thing that creates
one — so removing a wrong one corrects our own figures, never a club's typing.

USAGE
-----
    cd /srv/docker
    export COMPOSE_PROJECT_NAME=bltbox_docker_app

    # dry run, one club — read this first
    docker compose exec -T betterstats-backend \\
      python -m app.scripts.reconcile_milestones shoalwater-bay-cricket-club

    docker compose exec -T betterstats-backend \\
      python -m app.scripts.reconcile_milestones shoalwater-bay-cricket-club --apply

    # every club
    docker compose exec -T betterstats-backend \\
      python -m app.scripts.reconcile_milestones all

Dry run by default, per the house rule.
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select

from app.models.db import Organisation, Player, async_session_maker
from app.services.sync import _compute_milestones


async def _clubs(session, target: str) -> list[Organisation]:
    if target.lower() == "all":
        return list((await session.execute(
            select(Organisation).where(Organisation.archived_at.is_(None))
            .order_by(Organisation.name))).scalars())
    try:
        club = await session.get(Organisation, uuid.UUID(target))
    except (ValueError, AttributeError):
        club = (await session.execute(
            select(Organisation).where(Organisation.slug == target))).scalar_one_or_none()
    return [club] if club else []


async def run(target: str, apply: bool) -> int:
    async with async_session_maker() as session:
        clubs = await _clubs(session, target)
        club_refs = [(c.id, c.name, c.slug) for c in clubs]
    if not club_refs:
        print(f"No club found for {target!r}")
        return 1

    total_added = total_removed = 0
    for club_id, name, slug in club_refs:
        async with async_session_maker() as session:
            rows = (await session.execute(
                select(Player.id, Player.display_name_override, Player.name)
                .where(Player.organisation_id == club_id))).all()
            names = {str(pid): (override or name) for pid, override, name in rows}
            if not names:
                continue
            report = await _compute_milestones(
                session, list(names), club_id, reconcile=True, dry_run=not apply)
        added, removed = report["added"], report["removed"]
        if not added and not removed:
            continue
        total_added += len(added)
        total_removed += len(removed)
        print(f"\n{name} ({slug})")
        for pid, mt, value in sorted(removed, key=lambda x: (names.get(x[0], ""), x[1], x[2])):
            print(f"  REMOVE  {names.get(pid, pid):<32} {value:>6,} {mt}")
        for pid, mt, value in sorted(added, key=lambda x: (names.get(x[0], ""), x[1], x[2])):
            print(f"  ADD     {names.get(pid, pid):<32} {value:>6,} {mt}")

    verb = "" if apply else "would be "
    print(f"\n{total_removed} milestone(s) {verb}removed, {total_added} {verb}added.")
    if not apply:
        print("DRY RUN — nothing changed. Re-run with --apply to write it.")
    return 0


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(run(args[0], "--apply" in sys.argv)))


if __name__ == "__main__":
    main()
