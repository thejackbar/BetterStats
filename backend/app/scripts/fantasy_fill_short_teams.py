"""Fill Fantasy teams that are short of players with the top scorers in the pool.

For picks that cannot be recovered. Each missing place gets the pool player with the
most season points that the team does not already hold, taking the role the team is
short of first. The lock and budget are ignored. Dry run by default; --apply writes,
adds an audit entry per team and scores the rounds again.

    python -m app.scripts.fantasy_fill_short_teams <org-id-or-slug> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import fantasy_fill_short as fill


async def run(org: str, apply: bool) -> None:
    async with async_session_maker() as db:
        row = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).first()
        if row is None:
            raise SystemExit(f"no club matches {org!r}")
        club_id, name = row
        plans = await fill.plan_fill(db, club_id)
        print(f"\n{name}")
        if not plans:
            print("  No team is short of players.")
            return
        total = 0
        for p in plans:
            print(f"  {p['team_name']} ({p['has']} of {p['size']} players):")
            for c in p["adds"]:
                print(f"    {'add' if apply else 'would add'}: {c['name']} ({c['role']}, {float(c['total_points']):g} pts)")
            if len(p["adds"]) < p["size"] - p["has"]:
                print("    WARNING: the pool ran out of players to add.")
            total += len(p["adds"])
        if plans and all(float(c["total_points"]) == 0 for p in plans for c in p["adds"]):
            print("\n  Note: every player chosen has 0 points, so the choice fell to price. The season may not have started.")
        if apply:
            await fill.apply_fill(db, club_id, plans)
            await db.commit()
            print(f"\nAdded {total} player(s).")
        else:
            await db.rollback()
            print(f"\nDry run: {total} player(s) would be added. Run again with --apply.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.fantasy_fill_short_teams <org-id-or-slug> [--apply]")
    asyncio.run(run(args[0], "--apply" in sys.argv))
