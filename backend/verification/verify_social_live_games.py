"""BetterSocials: games still in play on the Team of the Round and the Results roundup, against a real Postgres.

Runs the SHIPPED service functions and route bodies, with only the Cricket Australia client stubbed to a
small hand-built Saturday:

  1st Grade v Rivals     COMPLETED   Sam 87 off 54 + 2 wkts + 1 maiden, Bo 4 wkts + 2 maidens
  2nd Grade v Others     IN PLAY     Eli 100 not out, the opposition yet to bat
  3rd Grade v Others     IN PLAY     nothing on the card yet (no innings)

A team of the WEEK must stay exactly what it was (the in-play games are not in it). A team of the ROUND
counts them, flags them, and re-reads their cards fresh. Results with `include_live` shows the in-play
game as a LIVE row whose absent side reads `-`; without it, nothing changes.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/totw_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_social_live_games.py
A control run on the commit before this feature reports the new checks as FAIL (the arguments do not
exist) rather than crashing.
"""
from __future__ import annotations

import asyncio
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


ORG, OPP_ORG = uuid.uuid4(), uuid.uuid4()
GRADE_A, GRADE_B, GRADE_C = (str(uuid.uuid4()) for _ in range(3))
SAT = date.today() - timedelta(days=1)
P = {n: str(uuid.uuid4()) for n in ("sam", "bo", "eli", "opp")}
NAME = {"sam": "Sam Star", "bo": "Bo Bowler", "eli": "Eli Ton", "opp": "Otto Opposition"}
M_DONE, M_LIVE, M_EMPTY = (str(uuid.uuid4()) for _ in range(3))
OUR_TEAM, THEIR_TEAM = "aaaaaaaa-0000-0000-0000-000000000001", "bbbbbbbb-0000-0000-0000-000000000002"


def bat(who, r, b, out="caught", out_id=2):
    return {"participantId": P[who], "playerShortName": NAME[who], "runsScored": r, "ballsFaced": b,
            "foursScored": 0, "sixesScored": 0, "dismissalType": out, "dismissalTypeId": out_id}


def bowl(who, overs, m, r, w):
    return {"participantId": P[who], "playerShortName": NAME[who], "oversBowled": overs,
            "maidensBowled": m, "runsConceded": r, "wicketsTaken": w}


def card(grade, innings, result):
    roster = [{"participantId": P[k], "displayName": NAME[k], "playerShortName": NAME[k], "roles": []}
              for k in P if k != "opp"]
    return {
        "grade": {"name": grade},
        "matchSummary": {"round": {"name": "Round 5"}, "result": result,
                         "teams": [{"id": OUR_TEAM, "isWinner": result.startswith("Applecross won")},
                                   {"id": THEIR_TEAM}],
                         "dateTimeUTC": f"{SAT.isoformat()}T03:00:00Z"},
        "teams": [{"id": OUR_TEAM, "displayName": "Applecross Cricket Club", "owningOrganisation": {"id": str(ORG)}, "players": roster},
                  {"id": THEIR_TEAM, "displayName": "Rivals CC", "owningOrganisation": {"id": str(OPP_ORG)}, "players": []}],
        "innings": innings,
    }


CARDS = {
    M_DONE: card("1st Grade", [
        {"battingTeamId": OUR_TEAM, "runsScored": 200, "numberOfWicketsFallen": 6, "batting": [bat("sam", 87, 54)], "bowling": [], "fielding": []},
        {"battingTeamId": THEIR_TEAM, "runsScored": 180, "numberOfWicketsFallen": 10, "batting": [bat("opp", 20, 30)],
         "bowling": [bowl("sam", "8.0", 1, 30, 2), bowl("bo", "10.0", 2, 25, 4)], "fielding": []},
    ], "Applecross won by 20 runs"),
    # In play: we are 3/210 and Eli is 100 not out; they have not batted.
    M_LIVE: card("2nd Grade", [
        {"battingTeamId": OUR_TEAM, "runsScored": 210, "numberOfWicketsFallen": 3,
         "batting": [bat("eli", 100, 80, out="not out", out_id=1)], "bowling": [], "fielding": []},
    ], ""),
    M_EMPTY: card("3rd Grade", [], ""),
}


def raw_match(mid, grade_guid, status):
    return {"id": mid, "statusId": status, "matchSchedule": [{"startDateTime": f"{SAT.isoformat()}T13:00:00"}],
            "round": {"name": "Round 5"}, "venue": {"name": "Oval"}, "grade": {"id": grade_guid},
            "teams": [{"displayName": "Applecross Cricket Club", "isHome": True, "owningOrganisation": {"id": str(ORG)}},
                      {"displayName": "Rivals CC", "isHome": False, "owningOrganisation": {"id": str(OPP_ORG)}}]}


GRADE_MATCHES = {
    GRADE_A: [raw_match(M_DONE, GRADE_A, 3)],
    GRADE_B: [raw_match(M_LIVE, GRADE_B, 2)],
    GRADE_C: [raw_match(M_EMPTY, GRADE_C, 2)],
}
CALLS: list[tuple[str, bool]] = []


async def _grade_matches(grade_id, force=False):
    return GRADE_MATCHES.get(grade_id, [])


async def _scorecard(match_id, force=False):
    CALLS.append((match_id, bool(force)))
    return CARDS.get(match_id)


async def _detail(match_id, force=False):
    for lst in GRADE_MATCHES.values():
        for m in lst:
            if m["id"] == match_id:
                return m
    return None


gr.get_grade_matches = _grade_matches
gr.get_match_scorecard = _scorecard
gr.get_match_detail = _detail


async def attempt(fn, *args, **kwargs):
    """Call, answering `unsupported` instead of raising on a build that predates the argument, so a control
    run reports the new checks as FAIL rather than crashing."""
    try:
        return await fn(*args, **kwargs)
    except TypeError as exc:
        return {"kind": f"unsupported: {exc}"}


async def main():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_name TEXT NOT NULL, alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ
            )
        """))

    season = uuid.uuid4()
    async with Session() as db:
        db.add_all([
            Organisation(id=ORG, name="Applecross Cricket Club", short_name="Applecross", slug="applecross",
                         is_active=True, module_overrides=["socials"]),
            Season(id=season, organisation_id=ORG, name="2025/26", year=date.today().year),
        ])
        await db.flush()
        db.add_all([
            Grade(id=uuid.uuid4(), season_id=season, name="1st Grade", grassroots_id=GRADE_A),
            Grade(id=uuid.uuid4(), season_id=season, name="2nd Grade", grassroots_id=GRADE_B),
            Grade(id=uuid.uuid4(), season_id=season, name="3rd Grade", grassroots_id=GRADE_C),
        ])
        await db.flush()
        for k in ("sam", "bo", "eli"):
            db.add(Player(id=uuid.uuid4(), organisation_id=ORG, name=NAME[k].split()[1] + ", " + NAME[k].split()[0],
                          grassroots_id=P[k]))
        await db.commit()

    async with Session() as db:
        org = await db.get(Organisation, ORG)

        print("\n── Team of the week: unchanged, finished games only ──")
        wk = await social_rounds.social_totw(db, org, "")
        pl = {p["last"]: p for p in wk.get("players", [])}
        check("the week holds the finished game's players only", sorted(pl), ["Bowler", "Star"])
        check("  ... one match", wk.get("matches"), 1)
        check("  ... no performer is flagged live", all("live" not in p for p in wk["players"]))
        check("  ... the default mode is week", (wk.get("mode"), wk.get("liveMatches")), ("week", 0))
        check("an unknown mode falls back to week", (await attempt(social_rounds.social_totw, db, org, "", mode="nonsense")).get("mode"), "week")

        print("\n── Team of the round: games in play count ──")
        CALLS.clear()
        rd = await attempt(social_rounds.social_totw, db, org, "", mode="round")
        pl = {p["last"]: p for p in rd.get("players", [])}
        check("the round answers as a round", rd.get("kind"), "round")
        check("it pooled the finished game and both in-play games", rd.get("matches"), 3)
        check("  ... of which two are in play", rd.get("liveMatches"), 2)
        check("  ... mode is echoed", rd.get("mode"), "round")
        check("the in-play century is in the team", "Ton" in pl)
        check("  ... flagged live, with his 100 as points", (pl.get("Ton", {}).get("live"), pl.get("Ton", {}).get("points")), (True, 100))
        check("  ... and the finished game's players are not flagged", "live" not in pl.get("Star", {"live": 1}))
        check("ranked best first across both", [p["last"] for p in rd.get("players", [])][:3], ["Star", "Ton", "Bowler"])
        live_ids = {M_LIVE, M_EMPTY}
        check("a card in play is read fresh, a finished one from the cache",
              {m: f for m, f in CALLS}, {M_DONE: False, M_LIVE: True, M_EMPTY: True})

        print("\n── Team of the round: a period and a pasted link ──")
        yest = SAT.isoformat()
        rng_wk = await social_rounds.social_totw(db, org, "", yest, yest)
        rng_rd = await attempt(social_rounds.social_totw, db, org, "", yest, yest, mode="round")
        check("a period in week mode leaves the games in play out", rng_wk.get("matches"), 1)
        check("  ... in round mode takes them", (rng_rd.get("matches"), rng_rd.get("liveMatches")), (3, 2))
        by_link_wk = await social_rounds.social_totw(db, org, M_DONE)
        by_link_rd = await attempt(social_rounds.social_totw, db, org, M_DONE, mode="round")
        check("a link in week mode leaves them out", by_link_wk.get("matches"), 1)
        check("  ... in round mode takes them", (by_link_rd.get("matches"), by_link_rd.get("liveMatches")), (3, 2))
        jr = await attempt(social_rounds.social_totw, db, org, "", yest, yest, "junior", "round")
        check("a scope with no matches says so in round words", jr.get("message"), "No completed or in-progress junior matches found for that round yet.")

        print("\n── Results: games in play as LIVE rows ──")
        base = await social_rounds.social_results(db, org)
        rows = [r for d in base["dates"] for r in d["results"]]
        check("results without the option are the finished game only", [r["grade"] for r in rows], ["1ST GRADE"])
        check("  ... its row carries no live key", "live" not in rows[0])
        CALLS.clear()
        withlive = await attempt(social_rounds.social_results, db, org, include_live=True)
        rows = {r["grade"]: r for d in withlive.get("dates", []) for r in d["results"]}
        check("with the option the game in play is a row too", sorted(rows), ["1ST GRADE", "2ND GRADE"])
        live = rows.get("2ND GRADE", {})
        check("  ... its outcome is LIVE and it says IN PROGRESS", (live.get("outcome"), live.get("margin"), live.get("live")), ("LIVE", "IN PROGRESS", True))
        check("  ... our score so far, and a dash for the side yet to bat", (live.get("us"), live.get("them")), ("3/210", "-"))
        check("  ... Eli's 100 is its top bat", "100" in str((live.get("topBat") or [{}])[0]), True)
        check("a game in play with no innings is left out", "3RD GRADE" not in rows)
        check("the finished row is untouched by the option", (rows.get("1ST GRADE", {}).get("outcome"), rows.get("1ST GRADE", {}).get("margin"), "live" in rows.get("1ST GRADE", {})), ("W", "BY 20 RUNS", False))
        check("the in-play cards were read fresh", {m: f for m, f in CALLS}.get(M_LIVE), True)
        linked = await attempt(social_rounds.social_results_for_reference, db, org, M_DONE, include_live=True)
        lrows = {r["grade"]: r for d in linked.get("dates", []) for r in d["results"]}
        check("a pasted link takes the games in play too", sorted(lrows), ["1ST GRADE", "2ND GRADE"])
        plain = await social_rounds.social_results_for_reference(db, org, M_DONE)
        check("  ... and without the option it does not", [r["grade"] for d in plain["dates"] for r in d["results"]], ["1ST GRADE"])

        print("\n── The route bodies ──")
        from app.routers import admin
        r1 = await attempt(admin.get_social_results, "", True, db, org)
        check("the results route passes live through", sorted(x["grade"] for d in r1.get("dates", []) for x in d["results"]), ["1ST GRADE", "2ND GRADE"])
        r2 = await attempt(admin.get_social_results, "", False, db, org)
        check("  ... and off by default", [x["grade"] for d in r2.get("dates", []) for x in d["results"]], ["1ST GRADE"])
        t1 = await attempt(admin.get_social_totw, "", db, org, "", "", "all", "round")
        check("the team route passes the mode through", (t1.get("mode"), t1.get("matches")), ("round", 3))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
