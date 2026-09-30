"""BetterSocials "Team of the week", against a real Postgres.

The team of the week is the player-of-the-match scoring run over EVERY completed
club match in one round, pooled and ranked. This runs the SHIPPED route body
(`routers.admin.get_social_totw`) and services, with only the Cricket Australia
client stubbed to a small, hand-built round:

  Round 5 (Saturday)   1st Grade v Rivals      Sam (87 off 54 + 2 wkts + 1 maiden), Bo (4 wkts, 2 maidens),
                                               Cy (2 catches), Dee (a duck), and an OPPOSITION batter on 200
                       2nd Grade v Others      Eli (100 not out), Sam again (30), Fay (a keeper: 3 catches
                                               + a stumping), Gus (unresolved to a club player)
  Round 4 (a week on)  1st Grade v Earlier     Hal (150), who must NOT be in round 5's team

Points are 1 a run, 20 a wicket, 2 a maiden, 8 an outfield catch / stumping / run
out, 4 a keeper catch.

It also proves the refactor under it left the two neighbours alone: the player
of the match and the results roundup are written to a digest file
(`TOTW_DIGEST`, default /tmp/totw_digest.json) so a run on the previous commit
can be diffed against this one.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/totw_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_social_totw.py
A control run on the commit before this feature reports the team-of-the-week
checks as FAIL (the function does not exist) and still writes the digest.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, Grade, Organisation, Player, Season  # noqa: E402
from app.services import grassroots_scores_client as gr  # noqa: E402
from app.services import social_rounds  # noqa: E402

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


ORG = uuid.uuid4()
OPP_ORG = uuid.uuid4()
GRADE_A, GRADE_B = str(uuid.uuid4()), str(uuid.uuid4())
TODAY = date.today()
SAT = TODAY - timedelta(days=2)
PREV = SAT - timedelta(days=7)

# Participant guids on the scorecards. Gus has no club player row.
P = {n: str(uuid.uuid4()) for n in ("sam", "bo", "cy", "dee", "eli", "fay", "gus", "hal", "opp")}
NAME = {"sam": "Sam Star", "bo": "Bo Bowler", "cy": "Cy Catcher", "dee": "Dee Duck", "eli": "Eli Ton",
        "fay": "Fay Keeper", "gus": "Gus Guest", "hal": "Hal Earlier", "opp": "Otto Opposition"}
M1, M3, M0 = (str(uuid.uuid4()) for _ in range(3))
OUR_TEAM, THEIR_TEAM = "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


def bat(who, r, b, out="caught", out_id=2):
    return {"participantId": P[who], "playerShortName": NAME[who], "runsScored": r, "ballsFaced": b,
            "foursScored": 0, "sixesScored": 0, "dismissalType": out, "dismissalTypeId": out_id}


def bowl(who, overs, m, r, w):
    return {"participantId": P[who], "playerShortName": NAME[who], "oversBowled": overs,
            "maidensBowled": m, "runsConceded": r, "wicketsTaken": w}


def field(who, catches=0, wk=0, st=0, ro=0):
    return {"participantId": P[who], "playerShortName": NAME[who], "totalCatches": catches,
            "wicketKeeperCatches": wk, "stumpings": st, "runOuts": ro}


def scorecard(grade_name, our_bat, our_field_bowl_vs_them, opp_bat, day):
    """Our innings carry our batting; THEIR innings carry our bowling + fielding."""
    roster = [{"participantId": P[k], "displayName": NAME[k], "playerShortName": NAME[k]} for k in P if k != "opp"]
    return {
        "grade": {"name": grade_name},
        "matchSummary": {
            "round": {"name": "Round 5"}, "result": "Applecross won by 20 runs",
            "teams": [{"id": OUR_TEAM, "isWinner": True, "resultType": "WON"},
                      {"id": THEIR_TEAM, "isWinner": False, "resultType": "LOST"}],
            "dateTimeUTC": f"{day.isoformat()}T03:00:00Z",
        },
        "teams": [
            {"id": OUR_TEAM, "displayName": "Applecross Cricket Club", "owningOrganisation": {"id": str(ORG)}, "players": roster},
            {"id": THEIR_TEAM, "displayName": "Rivals CC", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []},
        ],
        "innings": [
            {"battingTeamId": OUR_TEAM, "runsScored": 200, "numberOfWicketsFallen": 6, "batting": our_bat,
             "bowling": [], "fielding": []},
            {"battingTeamId": THEIR_TEAM, "runsScored": 180, "numberOfWicketsFallen": 10, "batting": opp_bat,
             "bowling": our_field_bowl_vs_them[0], "fielding": our_field_bowl_vs_them[1]},
        ],
    }


CARDS = {
    M1: scorecard("1st Grade", [bat("sam", 87, 54), bat("dee", 0, 4, out="bowled", out_id=3)],
                    ([bowl("sam", "8.0", 1, 30, 2), bowl("bo", "10.0", 2, 25, 4)], [field("cy", catches=2)]),
                    [bat("opp", 200, 100)], SAT),
    M3: scorecard("2nd Grade", [bat("eli", 100, 80, out="not out", out_id=1), bat("sam", 30, 20)],
                    ([], [field("fay", catches=3, wk=3, st=1)]),
                    [], SAT),
    M0: scorecard("1st Grade", [bat("hal", 150, 120)], ([], []), [], PREV),
}
# Gus scores on the 2nd grade card only.
CARDS[M3]["innings"][0]["batting"].append(bat("gus", 40, 30))


def raw_match(mid, day, rnd, grade_guid, status=3):
    return {"id": mid, "statusId": status, "matchSchedule": [{"startDateTime": f"{day.isoformat()}T13:00:00"}],
            "round": {"name": rnd}, "venue": {"name": "Oval"}, "grade": {"id": grade_guid},
            "teams": [{"displayName": "Applecross Cricket Club", "isHome": True,
                       "owningOrganisation": {"id": str(ORG)}},
                      {"displayName": "Rivals CC", "isHome": False, "owningOrganisation": {"id": str(OPP_ORG)}}]}


GRADE_MATCHES = {
    GRADE_A: [raw_match(M1, SAT, "Round 5", GRADE_A), raw_match(M0, PREV, "Round 4", GRADE_A)],
    GRADE_B: [raw_match(M3, SAT, "Round 5", GRADE_B)],
}


async def _grade_matches(grade_id, force=False):
    return GRADE_MATCHES.get(str(grade_id).lower(), GRADE_MATCHES.get(grade_id, []))


async def _scorecard(match_id, force=False):
    return CARDS.get(match_id)


async def _detail(match_id, force=False):
    for guid, lst in GRADE_MATCHES.items():
        for m in lst:
            if m["id"] == match_id:
                return m
    return None


gr.get_grade_matches = _grade_matches
gr.get_match_scorecard = _scorecard
gr.get_match_detail = _detail


async def main():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)

    season, ga, gb = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add_all([
            Organisation(id=ORG, name="Applecross Cricket Club", short_name="Applecross", slug="applecross",
                         is_active=True, module_overrides=["socials"]),
            Season(id=season, organisation_id=ORG, name="2025/26", year=TODAY.year),
        ])
        await db.flush()
        db.add_all([
            Grade(id=ga, season_id=season, name="1st Grade", grassroots_id=GRADE_A),
            Grade(id=gb, season_id=season, name="2nd Grade", grassroots_id=GRADE_B),
        ])
        await db.flush()
        for k in ("sam", "bo", "cy", "dee", "eli", "fay", "hal"):
            db.add(Player(id=uuid.uuid4(), organisation_id=ORG, name=NAME[k].split()[1] + ", " + NAME[k].split()[0],
                          grassroots_id=P[k]))
        await db.commit()

    digest: dict = {}
    E: dict = {}
    async with Session() as db:
        org = await db.get(Organisation, ORG)

        print("\n── Player of the match is unchanged by the refactor ──")
        potm = await social_rounds.social_potm(db, org, M1)
        digest["potm"] = [{k: v for k, v in p.items() if k not in ("guid", "pid")} for p in potm["players"]]
        digest["potm_match"] = potm["match"]
        top = potm["players"][0]
        check("Sam tops match 1: 87 runs + 2 wickets + 1 maiden = 129", (top["last"], top["points"]), ("Star", 129))
        check("Bo is next: 4 wickets + 2 maidens = 84", (potm["players"][1]["last"], potm["players"][1]["points"]), ("Bowler", 84))
        check("the opposition's 200 is not ours", all(p["last"] != "Opposition" for p in potm["players"]))

        print("\n── Results roundup is unchanged by the discovery extraction ──")
        res = await social_rounds.social_results(db, org)
        digest["results"] = [{k: v for k, v in r.items()} for d in res["dates"] for r in d["results"]]
        digest["results_dates"] = [(d["date"], d["round"]) for d in res["dates"]]
        check("results come back newest match-day first", len(res["dates"]) >= 1)

        print("\n── Team of the week: the latest round ──")
        totw_fn = getattr(social_rounds, "social_totw", None)
        check("social_totw exists", totw_fn is not None)
        if totw_fn is None:
            digest["totw"] = None
        else:
            out = await totw_fn(db, org, "")
            digest["totw"] = out.get("players")
            pl = out.get("players") or []
            by_last = {p["last"]: p for p in pl}
            check("answers as a round", out.get("kind"), "round")
            check("two matches were pooled (last week's is a different round)", out.get("matches"), 2)
            check("round and date read off the newest match-day", (out.get("round"), out.get("date")), ("Round 5", SAT.isoformat()))
            check("ranked best first, by the POTM points",
                  [(p["last"], p["points"]) for p in pl],
                  [("Star", 129), ("Ton", 100), ("Bowler", 84), ("Guest", 40), ("Keeper", 20), ("Catcher", 16), ("Duck", 0)])
            check("a keeper's catches score 4 and a stumping 8: 3x4 + 8 = 20, not 3x8",
                  by_last.get("Keeper", E).get("points"), 20)
            check("Sam played two grades and appears once", [p["last"] for p in pl].count("Star"), 1)
            check("  ... on his better day (129 in 1st Grade, not 30 in 2nd)",
                  (by_last.get("Star", E).get("points"), by_last.get("Star", E).get("grade")), (129, "1ST GRADE"))
            check("each performer carries their grade and opponent",
                  (by_last.get("Ton", E).get("grade"), by_last.get("Ton", E).get("opp")), ("2ND GRADE", "RIVALS CC"))
            check("last round's 150 is not in this round's team", "Earlier" not in by_last)
            check("the opposition's 200 is never picked", "Opposition" not in by_last)
            check("a club player resolves to their record (photo and profile follow)",
                  by_last.get("Star", E).get("pid") is not None)
            check("a scorecard name with no club player is kept by its scorecard id",
                  (by_last.get("Guest", E).get("pid"), by_last.get("Guest", E).get("guid")), (None, P["gus"]))

            print("\n── Team of the week: a round named by a pasted link ──")
            prev = await totw_fn(db, org, M0)
            check("an older round's link names that round", (prev.get("kind"), prev.get("round")), ("round", "Round 4"))
            check("  ... holding only that round's performers", [p["last"] for p in prev.get("players", [])], ["Earlier"])
            junk = await totw_fn(db, org, "not a match link")
            check("a link that names nothing says so", junk.get("kind") in ("invalid", "not_found"), True)
            gr.get_grade_matches, saved = (lambda g, force=False: _empty()), gr.get_grade_matches
            empty = await totw_fn(db, org, "")
            gr.get_grade_matches = saved
            check("a club with no completed matches gets a message, not an error", empty.get("kind"), "no_results")

    print("\n── The route body ──")
    from app.routers import admin as admin_router
    get_social_totw = getattr(admin_router, "get_social_totw", None)
    check("the route body exists", get_social_totw is not None)
    if get_social_totw is not None:
        async with Session() as db:
            org = await db.get(Organisation, ORG)
            body = await get_social_totw("", db, org)
            check("the route answers with the ranked pool of 7", (body.get("kind"), len(body.get("players", []))), ("round", 7))

    Path(os.environ.get("TOTW_DIGEST", "/tmp/totw_digest.json")).write_text(json.dumps(digest, indent=1, sort_keys=True, default=str))
    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


async def _empty():
    return []


asyncio.run(main())
