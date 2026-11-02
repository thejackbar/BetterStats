"""Who would move up a rarity tier because of the career landmark lift? Read-only.

Since v9.139.2 a player's card rarity gets a small lift for the big career landmarks
(`player_cards.RATING_LANDMARKS`: 200 / 400 games, 300 / 500 wickets, 5,000 / 10,000 runs, 100 / 200
dismissals; one point each, at most 3). This builds each club's card snapshot, rates the same figures
with and without the lift, and prints every player whose rarity changes, with the tier they move to.
It writes nothing. The snapshot it builds is cached in this script's own process only, never in the server's.

  cd /srv/docker && export COMPOSE_PROJECT_NAME=bltbox_docker_app
  docker compose exec -T betterstats-backend python -u -m app.scripts.preview_card_milestone_lift <org_id_or_slug_or_all>
"""
import argparse
import asyncio

from sqlalchemy import text

from app.models.db import Organisation, async_session_maker
from app.scripts.audit_twelfth_man import _all_orgs, _resolve_org, say
from app.services import player_cards as cards


async def preview(org_id: str) -> tuple[int, int, int]:
    """Returns (players lifted, players who change tier, players in the pool)."""
    async with async_session_maker() as db:
        await db.execute(text("SET TRANSACTION READ ONLY"))
        club = await db.get(Organisation, org_id)
        snap = await cards.club_snapshot(db, club, fresh=True)
    figs = snap["figs"]
    with_lift = cards.rate_pool(figs)
    saved = cards.RATING_LANDMARKS
    cards.RATING_LANDMARKS = ()
    try:
        without = cards.rate_pool(figs)
    finally:
        cards.RATING_LANDMARKS = saved
    lifted = [(pid, without[pid], with_lift[pid]) for pid in figs if with_lift[pid]["score"] != without[pid]["score"]]
    moved = [row for row in lifted if row[1]["tier"] != row[2]["tier"]]
    for pid, old, new in sorted(moved, key=lambda r: -r[2]["score"]):
        name = (snap["people"].get(pid) or {}).get("name") or pid
        f = figs[pid]
        say(f"  {name:<32} {old['score']:>2} {old['tier']:<9} -> {new['score']:>2} {new['tier']:<9} "
            f"({f['matches']} games, {f['wickets']} wickets, {f['runs']} runs, {f['dismissals']} dismissals)")
    pooled = sum(1 for f in figs.values() if f["matches"] > 0)
    return len(lifted), len(moved), pooled


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("org", help="club id, slug, or `all`")
    args = ap.parse_args()
    orgs = await _all_orgs() if args.org == "all" else [(await _resolve_org(args.org), args.org)]
    total_lifted = total_moved = 0
    for org_id, label in orgs:
        say(f"\n######## {label}")
        try:
            lifted, moved, pooled = await preview(org_id)
        except Exception as exc:  # one club's trouble must not hide the others
            say(f"  skipped: {exc!r}")
            continue
        say(f"  {lifted} of {pooled} players get a lift, {moved} change tier")
        total_lifted += lifted
        total_moved += moved
    say(f"\nAll clubs: {total_lifted} players lifted, {total_moved} change tier. Nothing was written.")


if __name__ == "__main__":
    asyncio.run(main())
