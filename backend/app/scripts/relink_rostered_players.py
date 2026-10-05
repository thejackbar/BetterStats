"""Add the games sync dropped for rostered players whose Cricket Australia id it did not know.

A player on the team sheet under an id the club never stored (a new registration id, or a
player new to the club who only exists hand-added) had their game dropped, and a stored
game is never re-read for them. They show on the scorecard but score nothing in Fantasy.
This reads each of the club's synced games this season from Cricket Australia, finds
rostered players it can now recognise by full name (exactly one club player has that name)
who have no appearance in the stored game, and adds their appearance, batting, bowling and
fielding rows. Rows are only added; nothing is deleted or changed.

Dry run by default: it lists game by game who would be attached to which profile.
With --apply it adds the rows, then settles any Fantasy round whose points moved.

    python -m app.scripts.relink_rostered_players <org-id-or-slug> [--year 2026] [--apply]
"""
from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.scripts import fantasy_round_drift
from app.services import grassroots_scores_client as gr
from app.services import participant_relink as relink

PACE_SECONDS = 0.4


async def _paced_fetch(match_id: str):
    sc = await gr.get_match_scorecard(match_id)
    await asyncio.sleep(PACE_SECONDS)
    return sc


async def run(org: str, year: int | None, apply: bool) -> None:
    async with async_session_maker() as db:
        row = (await db.execute(text("SELECT id, name FROM organisations WHERE id::text = :o OR slug = :o"), {"o": org})).first()
        if row is None:
            raise SystemExit(f"no club matches {org!r}")
        club_id, name = row
        if year is None:
            year = (await db.execute(text(
                "SELECT COALESCE(MAX(season_year), EXTRACT(YEAR FROM NOW())::int) FROM fantasy_seasons WHERE organisation_id = :o"),
                {"o": club_id})).scalar()
        print(f"\n{name}, season {year}")
        found = await relink.plan(db, club_id, int(year), _paced_fetch)
        print(f"  Checked {found['games_checked']} synced game(s); {found['no_data']} had no data from Cricket Australia.")
        if not found["games"]:
            print("  Nothing to attach: every rostered player Cricket Australia names is already in the stored games.")
            await db.rollback()
            return
        for g in found["games"]:
            print(f"\n  {g['date']}  {g['match']}  [{g['grade']}]")
            for m in g["missing"]:
                print(f"    team sheet '{m['sheet_name']}' ({m['guid']})  ->  {m['player']} [{m['player_id']}]")
        if not apply:
            await db.rollback()
            print(f"\nDry run: {len(found['games'])} game(s) would get rows added. Run again with --apply.")
            return
        total = {"appearances": 0, "batting": 0, "bowling": 0, "fielding": 0}
        for g in found["games"]:
            wanted = {m["guid"]: uuid.UUID(m["player_id"]) for m in g["missing"]}
            n = await relink.attach(db, club_id, g["game_id"], g["scorecard"], wanted)
            for k, v in n.items():
                total[k] += v
        await db.commit()
        print(f"\nAdded {total['appearances']} appearance(s), {total['batting']} batting, {total['bowling']} bowling, {total['fielding']} fielding row(s).")
    await fantasy_round_drift.run(org, True)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        raise SystemExit("usage: python -m app.scripts.relink_rostered_players <org-id-or-slug> [--year 2026] [--apply]")
    yr = None
    if "--year" in sys.argv:
        yr = int(sys.argv[sys.argv.index("--year") + 1])
        args = [a for a in args if a != str(yr)]
    asyncio.run(run(args[0], yr, "--apply" in sys.argv))
