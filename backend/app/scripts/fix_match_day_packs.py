"""Take back unopened Match Day packs that went to players who were not playing that day.

Match Day packs were granted on every day between a two day game's first and last day (a weekend game played over two Saturdays
counted the days in between). They are now given only on a fixture's own days, the first and the last. This takes back the unopened
packs that were wrongly given. Opened packs are left alone: the cards are in the player's book.

    python -m app.scripts.fix_match_day_packs <club slug | all>            # dry run: counts only
    python -m app.scripts.fix_match_day_packs <club slug | all> --apply    # does it, and writes an audit entry per club

Run inside the betterstats-backend container (`docker compose exec`, from /srv/docker, with COMPOSE_PROJECT_NAME set).
"""
import asyncio
import sys

from sqlalchemy import select

from app.models.db import Organisation, async_session_maker
from app.services import audit_log, player_cards


async def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    if len(args) != 1:
        print(__doc__)
        sys.exit(1)
    async with async_session_maker() as db:
        q = select(Organisation)
        if args[0] != "all":
            q = q.where(Organisation.slug == args[0].lower())
        clubs = (await db.execute(q)).scalars().all()
        if not clubs:
            print(f"No club called {args[0]!r}.")
            sys.exit(1)
        total = 0
        for club in clubs:
            out = await player_cards.unwind_stray_match_day_packs(db, str(club.id), apply=apply)
            if not out["packs"]:
                continue
            total += out["packs"]
            print(f"{club.slug}: {out['packs']} unopened Match Day packs held by {out['players']} players" + (" (taken back)" if out["applied"] else ""))
            if out["applied"]:
                await audit_log.log_activity(db, org_id=club.id, action="player_card_match_day_unwound", target_type="organisation",
                                             target_id=str(club.id), details=out)
        await db.commit()
        print(f"{'Took back' if apply else 'Would take back'} {total} packs." + ("" if apply else " Add --apply to do it."))


if __name__ == "__main__":
    asyncio.run(main())
