"""Check Fantasy seasons against the draw and the scorecards. Read only: nothing is written.

For each club it prints what is wrong in plain sentences (see ``services/fantasy_audit``) or says the
season is healthy. ``all`` runs every club with a Fantasy season (the latest one each), politely paced:
one Cricket Australia call per grade per club, and none with --no-draw.

    python -m app.scripts.fantasy_audit <org-id-or-slug|all> [--no-draw]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import FantasySeason, async_session_maker
from app.services import fantasy_audit

PAUSE_SECONDS = 2.0


async def run(org: str, check_draw: bool) -> int:
    async with async_session_maker() as db:
        if org == "all":
            clubs = (await db.execute(text(
                "SELECT o.id, o.name FROM organisations o WHERE EXISTS "
                "(SELECT 1 FROM fantasy_seasons f WHERE f.organisation_id = o.id) ORDER BY o.name"))).all()
        else:
            clubs = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"),
                                      {"o": org})).all()
        if not clubs:
            raise SystemExit(f"no club matches {org!r}")
    unhealthy = 0
    for club_id, name in clubs:
        async with async_session_maker() as db:
            fs_id = (await db.execute(text(
                "SELECT id FROM fantasy_seasons WHERE organisation_id = :o ORDER BY season_year DESC LIMIT 1"),
                {"o": club_id})).scalar()
            if fs_id is None:
                print(f"\n{name}\n  No fantasy season.")
                continue
            fs = await db.get(FantasySeason, fs_id)
            try:
                res = await fantasy_audit.audit_season(db, fs, check_draw=check_draw)
            except Exception as e:  # noqa: BLE001
                print(f"\n{name}\n  Audit failed: {e}")
                unhealthy += 1
                continue
            await db.rollback()
        probs = fantasy_audit.problems(res)
        print(f"\n{name}  ({res['season_year']}: {res['rounds_scored']}/{res['rounds']} rounds confirmed"
              f"{'' if res['live_sync_on'] else ', live scoring OFF'})")
        if not probs:
            print("  Healthy.")
        else:
            unhealthy += 1
            for p in probs:
                print(f"  - {p}")
        if org == "all":
            await asyncio.sleep(PAUSE_SECONDS if check_draw else 0)
    print(f"\n{len(clubs)} club(s) checked, {unhealthy} with something to look at.")
    return unhealthy


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.fantasy_audit <org-id-or-slug|all> [--no-draw]")
    asyncio.run(run(args[0], "--no-draw" not in sys.argv))
