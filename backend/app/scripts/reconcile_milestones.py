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
import time
import uuid

from sqlalchemy import select

from collections import Counter

from sqlalchemy import text

from app.models.db import Organisation, Player, async_session_maker
from app.services import milestone_totals
from app.services.sync import _compute_milestones


async def _evidence(session, org_id, removed) -> dict:
    """For each proposed removal: when it was recorded, and what the player's
    figures are now (the profile's and the whole career's). A milestone minted
    during September 2026's double count, above both figures, is a phantom; one
    recorded years ago deserves a look before it is deleted."""
    pids = sorted({pid for pid, _, _ in removed})
    if not pids:
        return {}
    dates = {(str(p), t, v): d for p, t, v, d in (await session.execute(text(
        "SELECT player_id, milestone_type, milestone_value, achieved_at FROM milestones"
        " WHERE player_id = ANY(CAST(:p AS uuid[]))"), {"p": pids})).all()}
    prof = await milestone_totals.profile_totals(session, org_id, pids, with_split=False)
    whole = await milestone_totals.totals_under(session, org_id, pids, None)
    out = {}
    for pid, mt, value in removed:
        out[(pid, mt, value)] = (
            dates.get((pid, mt, value)),
            int(((prof.get(pid) or {}).get("totals") or {}).get(mt) or 0),
            int((whole.get(pid) or {}).get(mt) or 0),
        )
    return out


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

    total_added = total_removed = total_dated = 0
    many = len(club_refs) > 1
    for n, (club_id, name, slug) in enumerate(club_refs, 1):
        started = time.monotonic()
        async with async_session_maker() as session:
            # A reconcile reads the effective views many times over; JIT
            # compiling each of those plans costs more than running them.
            await session.execute(text("SET jit = off"))
            rows = (await session.execute(
                select(Player.id, Player.display_name_override, Player.name)
                .where(Player.organisation_id == club_id))).all()
            names = {str(pid): (override or name) for pid, override, name in rows}
            if not names:
                continue
            report = await _compute_milestones(
                session, list(names), club_id, reconcile=True, dry_run=True)
            added, removed = report["added"], report["removed"]
            dated = set(report.get("dated") or [])
            ev = await _evidence(session, club_id, removed)
        if apply and (added or removed):
            async with async_session_maker() as session:
                await session.execute(text("SET jit = off"))
                report = await _compute_milestones(
                    session, list(names), club_id, reconcile=True)
            added, removed = report["added"], report["removed"]
            dated = set(report.get("dated") or [])
        if many:
            # A club with nothing to change prints nothing else, so without this
            # a long run looks exactly like a stuck one.
            print(f"[{n}/{len(club_refs)}] {name}: {len(removed)} to remove,"
                  f" {len(added)} to add ({time.monotonic() - started:.1f}s)")
        if not added and not removed:
            continue
        total_added += len(added)
        total_removed += len(removed)
        total_dated += len(dated)
        print(f"\n{name} ({slug})")
        for pid, mt, value in sorted(removed, key=lambda x: (names.get(x[0], ""), x[1], x[2])):
            recorded, prof_v, whole_v = ev.get((pid, mt, value), (None, 0, 0))
            print(f"  REMOVE  {names.get(pid, pid):<32} {value:>6,} {mt:<8}"
                  f" recorded {str(recorded or '?'):<10}  now {max(prof_v, whole_v):,}"
                  f" (profile {prof_v:,}, whole career {whole_v:,})")
        when = Counter((ev.get(r, (None,))[0] or "unknown") for r in removed)
        if when:
            print("  Removals by the date they were recorded: "
                  + ", ".join(f"{d}: {n}" for d, n in sorted(when.items(), key=lambda x: str(x[0]))))
        for pid, mt, value in sorted(added, key=lambda x: (names.get(x[0], ""), x[1], x[2])):
            mark = "  dated today, will be announced" if (pid, mt, value) in dated else ""
            print(f"  ADD     {names.get(pid, pid):<32} {value:>6,} {mt:<8}{mark}")
        if added:
            print(f"  Additions dated today (announced as just reached): {len(dated)} of {len(added)}")

    verb = "" if apply else "would be "
    print(f"\n{total_removed} milestone(s) {verb}removed, {total_added} {verb}added"
          f" ({total_dated} dated today, the rest undated).")
    if not apply:
        print("DRY RUN — nothing changed. Re-run with --apply to write it.")
    return 0


def main() -> None:
    # Line-buffered, so a run redirected to a file can be followed with
    # `tail -f` rather than sitting empty until the last club is done.
    sys.stdout.reconfigure(line_buffering=True)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print(__doc__)
        sys.exit(2)
    sys.exit(asyncio.run(run(args[0], "--apply" in sys.argv)))


if __name__ == "__main__":
    main()
