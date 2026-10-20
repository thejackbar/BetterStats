"""List Fantasy pool players with no games this season, and who holds their stats.

Read only. A player added to the pool by hand has no games of their own; their real
games land on a separate synced record with the same name. Merge the pair (Players
> merge; the merge now carries their Fantasy picks and pool entry) and re-settle
the rounds, or type their scores in on Fantasy > Registered players.

    python -m app.scripts.fantasy_zero_stat_players <org-id-or-slug|all>
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import fantasy_pool_check as check


async def run(org: str) -> None:
    async with async_session_maker() as db:
        where = "" if org == "all" else " WHERE id::text = :o OR slug = :o"
        clubs = (await db.execute(text(f"SELECT id, name FROM organisations{where}"), {"o": org})).all()
        if not clubs:
            raise SystemExit(f"no club matches {org!r}")
        for club_id, name in clubs:
            rows = await check.zero_stat_pool_players(db, club_id)
            if not rows:
                continue
            print(f"\n{name}")
            for r in rows:
                tag = "added by hand" if r["added_by_hand"] else "in pool"
                if r["twins"]:
                    for t in r["twins"]:
                        print(f"  MERGE: {r['name']} ({tag}, picked in {r['picked_by']} teams, no games) "
                              f"-> keep the profile with {t['games']} games ({t['player_id']})")
                else:
                    print(f"  no match: {r['name']} ({tag}, picked in {r['picked_by']} teams, no games). "
                          f"No same-name profile has games; type their scores in if they have played.")


if __name__ == "__main__":
    asyncio.run(run(sys.argv[1] if len(sys.argv) > 1 else "all"))
