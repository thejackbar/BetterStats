"""The sync itself takes a late withdrawal off a recent game. Real Postgres, the real sync, Cricket Australia stubbed.

Reported by Applecross: Nuwani Jayaweera read 51 matches beside CA's 50, because of one game she was
named for and pulled out of. The sync stores an appearance for everyone on the team sheet it reads first, and
a stored game was never read for appearances again, so nothing removed her when CA took her off the sheet.

`verify_withdrawn_appearances.py` covers the rule, the guards, the figures and the backfill. This one runs
`sync_grassroots_game_level_data` itself, twice over the same game, to prove the hook is wired in and that it
keeps to recent games:

  RECENT  played 3 days ago, first stored while CA still had the card in play (so no appearance is judged:
          that is how Nuwani's row was written). The next sync, with the card COMPLETED and the sheet
          without Wanda, marks Wanda, and only Wanda, is_reserve TRUE with no slot
  JUDGED  a game first stored already COMPLETED has every appearance judged on the spot (FALSE and a slot).
          If CA later edits the sheet, the judgement stands: only an unjudged row is ever marked
  OLD     played 40 days ago: the same two syncs mark nobody (history goes through the backfill, with a plan)
  BACK    CA puts Wanda back on the sheet: the mark is cleared
  RERUN   a run with nothing new changes nothing

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/fantasy_test?host=/tmp&port=5439 \\
  python verification/verify_withdrawn_appearances_sync.py
"""
from __future__ import annotations

import asyncio
import copy
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Player
from app.services import grassroots_scores_client as grc

Session, check = base.Session, base.check
ORG, TODAY = base.ORG, base.TODAY

ROSE, WANDA, P3, P4 = (uuid.uuid4() for _ in range(4))
G_ROSE, G_WANDA, G_P3, G_P4, G_OPP = (str(uuid.uuid4()) for _ in range(5))
GUIDS = {"ROSE": (ROSE, G_ROSE), "WANDA": (WANDA, G_WANDA), "P3": (P3, G_P3), "P4": (P4, G_P4)}


def payload(game_id, days_ago: int, who: list[str], status: str = "COMPLETED") -> dict:
    sheet = [{"participantId": GUIDS[k][1], "playerShortName": k.title() + " Player", "roles": []} for k in who]
    return {
        "id": str(game_id), "grade": {"id": "g1", "name": "Firsts"}, "status": status,
        "matchSchedule": [{"startDateTime": (TODAY - timedelta(days=days_ago)).isoformat() + "T09:00:00Z"}],
        "matchSummary": {"teams": [{"id": "t1", "isHome": True, "displayName": "Alpha - 3s"},
                                   {"id": "t2", "isHome": False, "displayName": "Opp - 3s"}]},
        "teams": [{"id": "t1", "displayName": "Alpha - 3s", "owningOrganisation": {"id": str(ORG), "name": "Alpha CC"}, "players": sheet},
                  {"id": "t2", "displayName": "Opp - 3s", "owningOrganisation": {"id": "other", "name": "Opp CC"},
                   "players": [{"participantId": G_OPP, "playerShortName": "Oscar Opp"}]}],
        "innings": [{"inningsOrder": 1, "inningsNumber": 1, "battingTeamId": "t1",
                     "batting": [{"participantId": G_ROSE, "playerShortName": "C Rose", "batOrder": 1, "runsScored": 10, "ballsFaced": 12,
                                  "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b O Opp"}],
                     "bowling": [], "fielding": [], "fallOfWickets": []},
                    {"inningsOrder": 2, "inningsNumber": 2, "battingTeamId": "t2",
                     "batting": [{"participantId": G_OPP, "playerShortName": "O Opp", "batOrder": 1, "runsScored": 4, "ballsFaced": 6,
                                  "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b C Rose"}],
                     "bowling": [], "fielding": [], "fallOfWickets": []}],
    }


CURRENT: dict[str, dict] = {}


async def run_sync() -> dict:
    from app.services.sync import sync_grassroots_game_level_data

    async def grade_matches(_g):
        return [{"id": mid, "matchSchedule": p["matchSchedule"], "status": "COMPLETED",
                 "teams": [{"owningOrganisation": {"id": str(ORG)}}, {"owningOrganisation": {"id": "other"}}]}
                for mid, p in CURRENT.items()]

    async def scorecard(mid, force=False):
        return copy.deepcopy(CURRENT.get(str(mid)))

    grc.get_grade_matches, grc.get_match_scorecard = grade_matches, scorecard
    return await sync_grassroots_game_level_data(str(ORG))


async def flags(game_id) -> dict:
    async with Session() as s:
        rows = (await s.execute(text("SELECT player_id, is_reserve, sheet_slot FROM game_appearances WHERE game_id = :g"),
                                {"g": game_id})).all()
    names = {v[0]: k for k, v in GUIDS.items()}
    return {names[r[0]]: (r[1], r[2]) for r in rows if r[0] in names}


async def audits() -> int:
    async with Session() as s:
        return (await s.execute(text("SELECT COUNT(*) FROM audit_logs WHERE action = 'sync_withdrawn_appearances'"))).scalar()


async def main() -> int:
    await base.build_schema()
    async with base.engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY, created_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL, user_id UUID,
            action TEXT NOT NULL, target_type TEXT, target_id TEXT, details JSONB DEFAULT '{}')"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID, keep_player_id UUID, keep_player_name TEXT,
            removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
            canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    await base.seed()
    async with Session() as s:
        s.add_all([Player(id=pid, name=f"{k.title()}, Player", organisation_id=ORG, grassroots_id=g) for k, (pid, g) in GUIDS.items()])
        await s.commit()

    recent, old, judged = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    everyone = ["ROSE", "WANDA", "P3", "P4"]
    without = ["ROSE", "P3", "P4"]

    print("\n-- FIRST SYNC: THE SHEET AS IT WAS WHILE THE GAME WAS IN PLAY --")
    CURRENT[str(recent)] = payload(recent, 3, everyone, "IN PROGRESS")
    CURRENT[str(old)] = payload(old, 40, everyone, "IN PROGRESS")
    CURRENT[str(judged)] = payload(judged, 3, everyone, "COMPLETED")
    await run_sync()
    f1, f_old1, f_j1 = await flags(recent), await flags(old), await flags(judged)
    check("the recent game stores all four appearances, none judged", set(f1) == set(everyone) and all(v == (None, None) for v in f1.values()), str(f1))
    check("the old game does too", set(f_old1) == set(everyone) and all(v == (None, None) for v in f_old1.values()), str(f_old1))
    check("a game first stored COMPLETED is judged on the spot: nobody is NULL", all(v[0] is False and v[1] for v in f_j1.values()) and len(f_j1) == 4, str(f_j1))

    print("\n-- SECOND SYNC: THE CARD IS COMPLETED AND CA HAS TAKEN WANDA OFF THE FINAL SHEET --")
    CURRENT[str(recent)] = payload(recent, 3, without)
    CURRENT[str(old)] = payload(old, 40, without)
    CURRENT[str(judged)] = payload(judged, 3, without)
    stats = await run_sync()
    f2, f_old2, f_j2 = await flags(recent), await flags(old), await flags(judged)
    check("RECENT: Wanda is marked withdrawn (TRUE, no slot)", f2.get("WANDA") == (True, None), str(f2))
    check("RECENT: the three still on the sheet are untouched", all(f2[k] == (None, None) for k in without), str(f2))
    check("OLD: a game outside the two-week window is left to the backfill", all(v == (None, None) for v in f_old2.values()), str(f_old2))
    check("JUDGED: a judgement the sync made from the final sheet stands, even if the sheet is edited later", f_j2 == f_j1, str(f_j2))
    check("the run reports one withdrawal", stats.get("gr_appearances_withdrawn") == 1, str({k: v for k, v in stats.items() if "appear" in k}))
    check("one audit entry, so it can be undone", await audits() == 1, str(await audits()))
    async with Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE game_id = :g"), {"g": recent})).scalar()
    check("nothing was deleted: the row is still there to restore", n == 4, str(n))

    print("\n-- A RUN WITH NOTHING NEW --")
    stats = await run_sync()
    check("the same sheet again changes nothing and writes no second entry",
          await flags(recent) == f2 and await audits() == 1 and not stats.get("gr_appearances_withdrawn"), str(stats.get("gr_appearances_withdrawn")))

    print("\n-- CA PUTS WANDA BACK --")
    CURRENT[str(recent)] = payload(recent, 3, everyone)
    stats = await run_sync()
    f3 = await flags(recent)
    check("the mark is cleared and she counts again", f3.get("WANDA") == (None, None), str(f3))
    check("the run reports it", stats.get("gr_appearances_restored") == 1, str(stats.get("gr_appearances_restored")))

    await base.engine.dispose()
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
