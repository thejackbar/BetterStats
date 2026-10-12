"""Replay a club's scored Fantasy rounds into player prices.

Prices move after every scored round (services/fantasy_pricing), and the nightly
job catches a season up on its own. Use this to see the moves first, or to catch up
now rather than after tonight's run. Prices are derived from each player's starting
price and the rounds scored, so running it twice changes nothing the second time and
a wrong move is undone by fixing the scores and running it again. A price an admin
typed in by hand is never touched. Dry run by default; --apply writes.

    python -m app.scripts.fantasy_recompute_prices <org-id-or-slug|all> [--apply]
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import text

from app.models.db import FantasySeason, async_session_maker
from app.services import fantasy_pricing


async def run(org: str, apply: bool) -> None:
    async with async_session_maker() as db:
        if org == "all":
            clubs = (await db.execute(text("SELECT id, name FROM organisations ORDER BY name"))).all()
        else:
            clubs = (await db.execute(
                text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).all()
            if not clubs:
                raise SystemExit(f"no club matches {org!r}")
        total = 0
        for club_id, name in clubs:
            seasons = (await db.execute(
                text("SELECT id FROM fantasy_seasons WHERE organisation_id = :o ORDER BY season_year"), {"o": club_id})).scalars().all()
            for sid in seasons:
                fs = await db.get(FantasySeason, sid)
                res = await fantasy_pricing.recompute_prices(db, fs, apply=apply)
                if not res["rounds"] and not res["changed"]:
                    continue
                names = {str(r[0]): r[1] for r in (await db.execute(
                    text("SELECT id, name FROM players WHERE id = ANY(CAST(:ids AS uuid[]))"),
                    {"ids": [m["player_id"] for m in res["moves"]]})).all()} if res["moves"] else {}
                print(f"\n{name}, {fs.season_year}: {res['rounds']} scored round(s), {res['players']} priced player(s), "
                      f"{res['changed']} {'moved' if apply else 'would move'}")
                for m in sorted(res["moves"], key=lambda m: -abs(m["after"] - m["before"]))[:10]:
                    print(f"    {names.get(m['player_id'], '?')}: {m['before']:.1f} -> {m['after']:.1f} (last round {m['change']:+.1f})")
                total += res["changed"]
        if apply:
            await db.commit()
            print(f"\nMoved {total} price(s).")
        else:
            await db.rollback()
            print(f"\nDry run: {total} price(s) would move. Run again with --apply.")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.fantasy_recompute_prices <org-id-or-slug|all> [--apply]")
    asyncio.run(run(args[0], "--apply" in sys.argv))
