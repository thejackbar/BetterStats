"""Verification: a rostered player whose Cricket Australia id the club never stored.
Real Postgres.

Reported (Scarborough): David Gardner and Ashton Taylor played, show on the scorecard, and
score nothing in Fantasy. The team sheet names them under participant ids the club has no
record under (Gardner's club record holds an older id; Ashton is hand-added with none), so
sync dropped their rows, and a stored game is never re-read for them. The public scorecard
also linked Ashton's "A Taylor" row to Angus Taylor, a different person, by surname and
initial.

Runs the SHIPPED `participant_names`, `participant_relink.plan/attach`, the Fantasy engine's
`_round_player_scores` and the `get_scorecard` route body (Grassroots stubbed).

CONTROL (`--control`): the `get_scorecard` route before this change (`CONTROL_REV`). It must
link Ashton's row to Angus.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_participant_relink.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import subprocess
import sys
import uuid
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlalchemy import text

import verify_fantasy_unsettle as base
from app.models.db import Player, Game, GameAppearance, BattingInnings, FantasySeason, FantasyRound, FantasyPoolPlayer
from app.services import fantasy_engine, grassroots_scores_client as grc, participant_names as pn, participant_relink as rl

Session, check = base.Session, base.check
ORG, ORG_B, FS_ID, R2, TODAY = base.ORG, base.ORG_B, base.FS_ID, base.R2, base.TODAY
CONTROL = "--control" in sys.argv
CONTROL_REV = "70dbd45"                      # the scorecard route and sync before the full-name link
REPO = Path(__file__).resolve().parent.parent.parent

ROSE, DG, ASH, ANGUS, OTHER_DG = (uuid.uuid4() for _ in range(5))
GUID_ROSE, GUID_DG_OLD, GUID_ANGUS = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
GUID_DG_NEW, GUID_ASH_NEW, GUID_OPP = str(uuid.uuid4()), str(uuid.uuid4()), str(uuid.uuid4())
GAME = uuid.uuid4()

PAYLOAD = {
    "id": str(GAME),
    "matchSummary": {"teams": [{"id": "t1", "isHome": True, "displayName": "Alpha - 3s"}, {"id": "t2", "isHome": False, "displayName": "Opp - 3s"}]},
    "teams": [
        {"id": "t1", "displayName": "Alpha - 3s", "owningOrganisation": {"id": str(ORG), "name": "Alpha CC"},
         "players": [{"participantId": GUID_ROSE, "playerShortName": "Cody Rose", "roles": ["Captain"]},
                     {"participantId": GUID_DG_NEW, "playerShortName": "David Gardner"},
                     {"participantId": GUID_ASH_NEW, "playerShortName": "Ashton Taylor"}]},
        {"id": "t2", "displayName": "Opp - 3s", "owningOrganisation": {"id": "other", "name": "Opp CC"},
         "players": [{"participantId": GUID_OPP, "playerShortName": "Oscar Opp"}]},
    ],
    "innings": [{
        "inningsOrder": 1, "inningsNumber": 1, "battingTeamId": "t1",
        "batting": [
            {"participantId": GUID_ROSE, "playerShortName": "C Rose", "batOrder": 1, "runsScored": 10, "ballsFaced": 12,
             "dismissalTypeId": 2, "dismissalType": "Bowled", "dismissalText": "b O Opp"},
            {"participantId": GUID_ASH_NEW, "playerShortName": "A Taylor", "batOrder": 2, "runsScored": 8, "ballsFaced": 9,
             "dismissalTypeId": 2, "dismissalType": "Caught", "dismissalText": "c O Opp b O Opp"},
            {"participantId": GUID_DG_NEW, "playerShortName": "D Gardner", "batOrder": 11, "dismissalTypeId": 99,
             "dismissalType": "Did not bat"},
        ],
        "bowling": [
            {"participantId": GUID_DG_NEW, "playerShortName": "D Gardner", "bowlOrder": 1, "oversBowled": 8, "maidensBowled": 1,
             "runsConceded": 43, "wicketsTaken": 0, "wideBalls": 5, "noBalls": 1, "economy": "5.37"},
            {"participantId": GUID_ASH_NEW, "playerShortName": "A Taylor", "bowlOrder": 2, "oversBowled": 7, "maidensBowled": 0,
             "runsConceded": 21, "wicketsTaken": 2, "economy": "3.0"},
        ],
        "fielding": [{"participantId": GUID_ASH_NEW, "playerShortName": "A Taylor", "totalCatches": 1, "wicketKeeperCatches": 0}],
        "fallOfWickets": [],
    }],
}


EXTRA: dict = {}


async def fetch(gid):
    return PAYLOAD if str(gid) == str(GAME) else EXTRA.get(str(gid))


def unit_checks() -> None:
    print("1. The name rule")
    check("'Taylor, Ashton' and 'Ashton Taylor' are one key", pn.full_name_key("Taylor, Ashton") == pn.full_name_key("Ashton Taylor"))
    check("an initial is not a full name", not pn.looks_full("D Gardner") and not pn.looks_full("********") and pn.looks_full("David Gardner"))
    check("a name two players share is not unique", "ashton taylor" not in pn.unique_by_full_name([(1, "Ashton Taylor"), (2, "Taylor, Ashton")]))
    check("Ashton and Angus are not the same given name; Dan and Daniel are",
          not pn.first_names_compatible("Ashton Taylor", "Taylor, Angus") and pn.first_names_compatible("Dan Baker", "Baker, Daniel"))
    uniq = {"david gardner": "P1"}
    sheet = [{"participantId": "g1", "playerShortName": "David Gardner"}]
    check("an unknown id with a unique full name is attached", pn.resolve_roster_by_name(sheet, {}, uniq) == {"g1": "P1"})
    check("a short name is never attached", pn.resolve_roster_by_name([{"participantId": "g1", "playerShortName": "D Gardner"}], {}, uniq) == {})
    check("a player already on the sheet under a known id is not attached again", pn.resolve_roster_by_name(sheet + [{"participantId": "g0", "playerShortName": "Dave"}], {"g0": "P1"}, uniq) == {})
    check("two unknown ids with one name attach to nobody", pn.resolve_roster_by_name(sheet + [{"participantId": "g2", "playerShortName": "David Gardner"}], {}, uniq) == {})


async def seed() -> None:
    await base.build_schema()
    async with base.engine.begin() as conn:
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID, keep_player_id UUID, keep_player_name TEXT,
            removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""CREATE TABLE IF NOT EXISTS grade_merge_logs (
            id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
            canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
    await base.seed()
    async with Session() as s:
        grade = (await s.execute(text("SELECT id FROM grades LIMIT 1"))).scalar()
        s.add_all([Player(id=ROSE, name="Rose, Cody", organisation_id=ORG, grassroots_id=GUID_ROSE),
                   Player(id=DG, name="Gardner, David", organisation_id=ORG, grassroots_id=GUID_DG_OLD),
                   Player(id=ASH, name="Ashton Taylor", organisation_id=ORG),                      # hand-added, no id
                   Player(id=ANGUS, name="Taylor, Angus", organisation_id=ORG, grassroots_id=GUID_ANGUS),
                   Player(id=OTHER_DG, name="David Gardner", organisation_id=ORG_B, grassroots_id=str(uuid.uuid4()))])
        await s.flush()
        s.add(Game(id=GAME, grade_id=grade, played_at=TODAY - timedelta(days=2), home_team="Alpha - 3s", away_team="Opp - 3s",
                   home_org_id=ORG, status="COMPLETED"))
        await s.flush()
        s.add(GameAppearance(game_id=GAME, player_id=ROSE, team_name="Alpha - 3s"))
        s.add(BattingInnings(game_id=GAME, player_id=ROSE, innings_number=1, runs=10, balls=12, fours=0, sixes=0,
                             dismissal_type="b", not_out=False))
        for p in (DG, ASH, ANGUS):
            s.add(FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=p, role="bowler",
                                    role_source="admin", base_price=5, current_price=5))
        await s.commit()
        # Sync keeps an unregistered fielder's catches under their name with no id.
        await s.execute(text("INSERT INTO fielding_stats (game_id, player_id, player_name, catches, catches_wk, run_outs, stumpings) "
                             "VALUES (:g, NULL, 'A Taylor', 1, 0, 0, 0)"), {"g": GAME})
        await s.commit()


async def scores() -> dict:
    async with Session() as s:
        fs = await s.get(FantasySeason, FS_ID)
        rnd = await s.get(FantasyRound, R2)
        out = await fantasy_engine._round_player_scores(s, fs, rnd)
        await s.rollback()
    return out


async def counts() -> dict:
    async with Session() as s:
        q = lambda sql: s.execute(text(sql), {"g": GAME})  # noqa: E731
        return {
            "app": (await q("SELECT COUNT(*) FROM game_appearances WHERE game_id=:g")).scalar(),
            "bat": (await q("SELECT COUNT(*) FROM batting_innings WHERE game_id=:g")).scalar(),
            "bowl": (await q("SELECT COUNT(*) FROM bowling_spells WHERE game_id=:g")).scalar(),
            "field": (await q("SELECT COUNT(*) FROM fielding_stats WHERE game_id=:g")).scalar(),
        }


def load_games_module():
    if not CONTROL:
        from app.routers import games
        return games
    src = subprocess.run(["git", "show", f"{CONTROL_REV}:backend/app/routers/games.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader("games_control", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__dict__["__name__"] = "games_control"
    exec(compile(src, "games_control.py", "exec"), mod.__dict__)
    return mod


def load_old_sync():
    """sync.py as it was (CONTROL_REV), to show the same team sheet dropping the two players."""
    src = subprocess.run(["git", "show", f"{CONTROL_REV}:backend/app/services/sync.py"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    spec = importlib.util.spec_from_loader("sync_control", loader=None)
    mod = importlib.util.module_from_spec(spec)
    mod.__dict__["__name__"] = "sync_control"
    exec(compile(src, "sync_control.py", "exec"), mod.__dict__)
    return mod


def payload_for(game_id) -> dict:
    import copy
    p = copy.deepcopy(PAYLOAD)
    p["id"] = str(game_id)
    p["grade"] = {"id": "g1", "name": "Firsts"}
    p["matchSchedule"] = [{"startDateTime": (TODAY - timedelta(days=3)).isoformat() + "T09:00:00Z"}]
    return p


async def run_sync(sync_fn, game_id) -> dict:
    """Run a game-level sync for one new match, Cricket Australia stubbed."""
    pl = payload_for(game_id)
    async def grade_matches(_g):
        return [{"id": str(game_id), "matchSchedule": pl["matchSchedule"], "status": "COMPLETED",
                 "teams": [{"owningOrganisation": {"id": str(ORG)}}, {"owningOrganisation": {"id": "other"}}]}]
    async def scorecard(mid, force=False):
        return pl if str(mid) == str(game_id) else None
    grc.get_grade_matches, grc.get_match_scorecard = grade_matches, scorecard
    await sync_fn(str(ORG))
    async with Session() as s:
        got = {}
        for name, pid in (("DG", DG), ("ASH", ASH), ("ROSE", ROSE)):
            got[name] = {
                "app": (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE game_id=:g AND player_id=:p"), {"g": game_id, "p": pid})).scalar(),
                "bowl": (await s.execute(text("SELECT COUNT(*) FROM bowling_spells WHERE game_id=:g AND player_id=:p"), {"g": game_id, "p": pid})).scalar(),
            }
        got["game"] = (await s.execute(text("SELECT COUNT(*) FROM games WHERE id=:g"), {"g": game_id})).scalar()
    return got


async def main() -> int:
    unit_checks()
    await seed()
    grc.get_match_scorecard = lambda gid, force=False: fetch(gid)

    print("2. Before: the two played and score nothing (the reported state)")
    sc = await scores()
    check("David Gardner has no score", str(DG) not in sc, repr(sc.get(str(DG))))
    check("Ashton Taylor has no score", str(ASH) not in sc, repr(sc.get(str(ASH))))
    check("a player whose id is known does score (so the absence above is meaningful)", str(ROSE) in sc, repr(list(sc)))
    before = await counts()

    print("3. The scorecard links the right person")
    games = load_games_module()
    async with Session() as s:
        card = await games.get_scorecard(str(GAME), s)
    bat = {r.get("player_name"): r.get("player_id") for r in card.get("batting", [])}
    ash_row = next((r for r in card.get("batting", []) if r.get("batting_position") == 2), {})
    dg_row = next((r for r in card.get("batting", []) if r.get("batting_position") == 11 or r.get("did_not_bat")), {})
    check("Ashton's 'A Taylor' row links to Ashton, not Angus", str(ash_row.get("player_id")) == str(ASH), repr(ash_row.get("player_id")))
    check("Angus is not shown as having batted", str(ANGUS) not in {str(r.get("player_id")) for r in card.get("batting", [])}, repr(bat))
    check("David's row links to his record", str(dg_row.get("player_id")) == str(DG), repr(dg_row.get("player_id")))
    if CONTROL:
        return base.FAIL

    print("4. The plan names who would be attached to which profile")
    async with Session() as s:
        found = await rl.plan(s, ORG, TODAY.year, fetch)
        await s.rollback()
    check("one game found", len(found["games"]) == 1, repr(found["games"] and len(found["games"])))
    who = {m["sheet_name"]: m["player_id"] for m in (found["games"][0]["missing"] if found["games"] else [])}
    check("David Gardner goes to his own record", who.get("David Gardner") == str(DG), repr(who))
    check("Ashton Taylor goes to the hand-added record, not Angus", who.get("Ashton Taylor") == str(ASH), repr(who))
    check("the other club's David Gardner is not considered", str(OTHER_DG) not in who.values())

    print("5. Attaching adds their rows and nothing else")
    async with Session() as s:
        wanted = {m["guid"]: uuid.UUID(m["player_id"]) for m in found["games"][0]["missing"]}
        n = await rl.attach(s, ORG, GAME, PAYLOAD, wanted)
        await s.commit()
    after = await counts()
    check("two appearances added", n["appearances"] == 2 and after["app"] == before["app"] + 2, repr((n, before, after)))
    check("batting: Ashton's score and David's did-not-bat row", n["batting"] == 2 and after["bat"] == before["bat"] + 2, repr((n, after)))
    check("bowling: both bowlers", n["bowling"] == 2 and after["bowl"] == before["bowl"] + 2, repr((n, after)))
    check("Ashton's catch goes on the existing nameless row, no second row", n["fielding"] == 1 and after["field"] == before["field"], repr((n, before, after)))
    async with Session() as s:
        rose = (await s.execute(text("SELECT runs FROM batting_innings WHERE game_id=:g AND player_id=:p"), {"g": GAME, "p": ROSE})).scalars().all()
        orphan = (await s.execute(text("SELECT player_id, player_name FROM fielding_stats WHERE game_id=:g"), {"g": GAME})).first()
    check("Rose's own row is untouched", rose == [10], repr(rose))
    check("the catch row now belongs to Ashton and has no stray name", orphan and str(orphan[0]) == str(ASH) and orphan[1] is None, repr(orphan))

    print("6. Fantasy now scores them")
    sc = await scores()
    check("Ashton scores", str(ASH) in sc and sc[str(ASH)]["total"] > 0, repr(sc.get(str(ASH))))
    check("David scores (an appearance and a maiden)", str(DG) in sc and sc[str(DG)]["total"] > 0, repr(sc.get(str(DG))))
    check("Angus, who did not play, does not", str(ANGUS) not in sc)

    print("7. Running it again changes nothing")
    async with Session() as s:
        again = await rl.attach(s, ORG, GAME, PAYLOAD, wanted)
        await s.commit()
    check("no rows added the second time", all(v == 0 for v in again.values()) and await counts() == after, repr((again, await counts())))
    async with Session() as s:
        found2 = await rl.plan(s, ORG, TODAY.year, fetch)
        await s.rollback()
    check("and the plan is empty", found2["games"] == [], repr(found2["games"]))

    print("8. Sync itself recognises them from now on (same team sheet, old sync against new sync)")
    old_game, new_game = uuid.uuid4(), uuid.uuid4()
    saved = grc.get_grade_matches, grc.get_match_scorecard
    try:
        control = await run_sync(load_old_sync().sync_grassroots_game_level_data, old_game)
        shipped_sync = __import__("app.services.sync", fromlist=["x"]).sync_grassroots_game_level_data
        shipped = await run_sync(shipped_sync, new_game)
    finally:
        grc.get_grade_matches, grc.get_match_scorecard = saved
    check("control: the old sync stored the game and Rose, and dropped David and Ashton",
          control["game"] == 1 and control["ROSE"]["app"] == 1 and control["DG"]["app"] == 0 and control["ASH"]["app"] == 0 and control["DG"]["bowl"] == 0, repr(control))
    check("the new sync stores the same game with David and Ashton on their own records",
          shipped["game"] == 1 and shipped["ROSE"]["app"] == 1 and shipped["DG"]["app"] == 1 and shipped["ASH"]["app"] == 1
          and shipped["DG"]["bowl"] == 1 and shipped["ASH"]["bowl"] == 1, repr(shipped))
    async with Session() as s:
        angus = (await s.execute(text("SELECT COUNT(*) FROM game_appearances WHERE game_id=:g AND player_id=:p"), {"g": new_game, "p": ANGUS})).scalar()
    check("and Angus Taylor, who was not on the sheet, got nothing", angus == 0, repr(angus))

    print("9. A player whose id a later merge resolves, in a game stored before the merge")
    # David's real case: his team-sheet id was redirected by a merge made after the game
    # was stored, so sync knows the id and still has no row for him in that game.
    red, g_red, game4 = uuid.uuid4(), str(uuid.uuid4()), uuid.uuid4()
    async with Session() as s:
        grade = (await s.execute(text("SELECT id FROM grades LIMIT 1"))).scalar()
        s.add(Player(id=red, name="Reg, Redirect", organisation_id=ORG, grassroots_id=str(uuid.uuid4())))
        await s.flush()
        s.add(Game(id=game4, grade_id=grade, played_at=TODAY - timedelta(days=1), home_team="Alpha - 4s", away_team="Opp - 4s",
                   home_org_id=ORG, status="COMPLETED"))
        await s.flush()
        s.add(GameAppearance(game_id=game4, player_id=ROSE, team_name="Alpha - 4s"))   # sync has stored our side here
        await s.execute(text("INSERT INTO merge_logs (org_id, keep_player_id, keep_player_name, removed_player_id, removed_player_name) "
                             "VALUES (:o, :k, 'Reg, Redirect', :r, 'Reg, Redirect')"), {"o": ORG, "k": red, "r": uuid.UUID(g_red)})
        await s.commit()
    p4 = {"id": str(game4), "teams": [{"id": "t1", "displayName": "Alpha - 4s", "owningOrganisation": {"id": str(ORG)},
                                       "players": [{"participantId": GUID_ROSE, "playerShortName": "Cody Rose"}, {"participantId": g_red, "playerShortName": "R Reg"}]}],
          "innings": [{"inningsOrder": 1, "batting": [], "bowling": [{"participantId": g_red, "playerShortName": "R Reg", "oversBowled": 4,
                                                                       "maidensBowled": 0, "runsConceded": 12, "wicketsTaken": 1}], "fielding": []}]}
    EXTRA[str(game4)] = p4
    async with Session() as s:
        found4 = await rl.plan(s, ORG, TODAY.year, fetch)
        await s.rollback()
    hit = next((g for g in found4["games"] if g["game_id"] == str(game4)), None)
    check("the plan lists the redirected player for that game", hit is not None and hit["missing"][0]["player_id"] == str(red), repr(found4["games"] and [g["game_id"] for g in found4["games"]]))
    async with Session() as s:
        n4 = await rl.attach(s, ORG, game4, p4, {g_red: red})
        await s.commit()
    check("and attaching gives them their appearance and bowling", n4["appearances"] == 1 and n4["bowling"] == 1, repr(n4))
    async with Session() as s:
        again = await rl.plan(s, ORG, TODAY.year, fetch)
        await s.rollback()
    check("after that the plan has nothing left for them", all(g["game_id"] != str(game4) for g in again["games"]))

    print("10. A game whose own side sync has not stored yet is left to sync")
    game5 = uuid.uuid4()
    async with Session() as s:
        grade = (await s.execute(text("SELECT id FROM grades LIMIT 1"))).scalar()
        s.add(Game(id=game5, grade_id=grade, played_at=TODAY - timedelta(days=1), home_team="Alpha - 5s", away_team="Opp - 5s",
                   home_org_id=ORG, status="COMPLETED"))
        await s.commit()
    EXTRA[str(game5)] = {"id": str(game5), "teams": [{"id": "t1", "displayName": "Alpha - 5s", "owningOrganisation": {"id": str(ORG)},
                         "players": [{"participantId": GUID_ROSE, "playerShortName": "Cody Rose"},
                                     {"participantId": GUID_ASH_NEW, "playerShortName": "Ashton Taylor"}]}], "innings": []}
    async with Session() as s:
        found5 = await rl.plan(s, ORG, TODAY.year, fetch)
        await s.rollback()
    check("no player of ours has an appearance, so nothing is attached (sync would collide with it)",
          all(g["game_id"] != str(game5) for g in found5["games"]), repr([g["game_id"] for g in found5["games"]]))
    check("and the game is reported as left to sync", any(d["game_id"] == str(game5) for d in found5["deferred"]), repr(found5["deferred"]))
    return base.FAIL


if __name__ == "__main__":
    failed = asyncio.run(main())
    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    sys.exit(1 if failed else 0)
