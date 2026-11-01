"""Pay the Winner Winner and Match Day packs a club's players have earned and not yet been granted. Dry run unless --apply.

Packs are granted when a player opens their page. This does the same for everyone in the card pool at once, by the same rules and
the same refs, so it can never pay twice and never pays what opening the page would not:

  * Winner Winner: every win finished before today, from the club's start day (`winner_packs_from`) or from `--winner-from` if that is
    earlier. A player opening their page only looks back 7 days; this does not, so it is how a backfill is done.
  * Match Day: a fixture whose own day is today (a first or last day), with the player on its confirmed team sheet, or a scorecard
    dated today.

`--winner-from DAY` lowers the club's Winner Winner start day (it never raises it), for a club whose start day was set after wins
it meant to pay. The default is yesterday in the club's own timezone. Pass `--winner-from none` to leave it alone.

    python -m app.scripts.catch_up_card_packs <club slug | all>                       # dry run: who would get what
    python -m app.scripts.catch_up_card_packs <club slug | all> --apply --by "name"    # does it, and writes an audit entry per club
    python -m app.scripts.catch_up_card_packs <club slug> --winner-from 2026-10-01      # backfill from 1 October

Run inside the betterstats-backend container (`docker compose exec`, from /srv/docker, with COMPOSE_PROJECT_NAME set).
"""
import argparse
import asyncio
from datetime import date, timedelta

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services import audit_log, player_cards


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("club", help="club slug, or all")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--by", default="", help="who ran it, for the audit entry")
    ap.add_argument("--winner-from", default="", help="YYYY-MM-DD, or none; default yesterday in the club's timezone")
    args = ap.parse_args()
    if args.apply and not args.by.strip():
        ap.error("--apply needs --by \"your name\"")
    async with async_session_maker() as db:
        q = select(Organisation)
        if args.club != "all":
            q = q.where(Organisation.slug == args.club.lower())
        clubs = (await db.execute(q)).scalars().all()
        if not clubs:
            print(f"No club called {args.club!r}.")
            raise SystemExit(1)
        for club in clubs:
            slug, club_id = club.slug, club.id
            settings = await player_cards.load_settings(db, str(club_id))
            if args.winner_from.lower() == "none":
                winner_from = None
            elif args.winner_from:
                winner_from = date.fromisoformat(args.winner_from)
            else:
                winner_from = player_cards.club_today(settings) - timedelta(days=1)
            out = await player_cards.catch_up_packs(db, club, apply=args.apply, winner_from=winner_from)
            if out.get("note"):
                print(f"{slug}: {out['note']}")
                continue
            print(f"{slug}: today {out['today']}, Winner Winner start day {out['winner_from']}")
            print(f"  Winner Winner: {len(out['winner'])} packs for {len({r['player'] for r in out['winner']})} players")
            for r in out["winner"]:
                print(f"    {r['player']}  (game {r['game'][:8]})")
            print(f"  Match Day: {len(out['match_day'])} packs")
            for r in out["match_day"]:
                print(f"    {r['player']}")
            for e in out["errors"]:
                print(f"  ERROR {e['player']}: {e['error']}")
            if args.apply and (out["winner"] or out["match_day"] or out["winner_from"]):
                await audit_log.log_activity(db, org_id=club_id, action="player_card_packs_caught_up", target_type="organisation", target_id=str(club_id),
                                             details={"by": args.by.strip(), "winner_packs": len(out["winner"]), "match_day_packs": len(out["match_day"]),
                                                      "winner_from": out["winner_from"], "errors": len(out["errors"])})
        if args.apply:
            await db.commit()
            print("Done.")
        else:
            await db.rollback()
            print("Nothing was written. Add --apply --by \"your name\" to do it.")


if __name__ == "__main__":
    asyncio.run(main())
