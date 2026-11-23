"""Performance Tracker (Association Socials), against a real Postgres.

Runs the SHIPPED route bodies in routers/performance.py with only the Cricket
Australia client stubbed, on a hand-built grade:

  Round 1 (done)      ALPHA v FOXTROT     Foxtrot (6th) won by 2 wickets: an upset, 5 places
                      BRAVO v ECHO        Bravo won by 3 runs: the closest match
                      CHARLIE v DELTA     abandoned: no result, never a result row
  Round 2 (upcoming)  ALPHA v BRAVO (1st v 2nd: match of the round), CHARLIE v FOXTROT, DELTA v ECHO

The Alpha card carries a hundred by a player typed in lower case, a did-not-bat
row, a filmed catch by the keeper (named in the dismissal by short name), a
filmed run out by two fielders, and a hat-trick five-for.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/podcast_verify?host=/var/tmp/pgv/sock&port=5544 \\
      python verification/verify_performance_tracker.py
A control run on the commit before this feature reports every check as FAIL
without crashing (no tracker module, no table).
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

from app.models.db import Base, Organisation  # noqa: E402
from app.services import grassroots_scores_client as gr  # noqa: E402

try:
    from app.routers import performance as pod  # noqa: E402
    from app.services.performance_ddl import STATEMENTS as POD_DDL  # noqa: E402
except Exception:  # the control commit has neither
    pod, POD_DDL = None, []
# The run sheet's table (migration 395), copied column for column, so the copy
# into the tracker can be shown to carry its rows across.
OLD_DDL = """
    CREATE TABLE IF NOT EXISTS podcast_episodes (
        id UUID PRIMARY KEY, organisation_id UUID NOT NULL REFERENCES organisations(id) ON DELETE CASCADE,
        episode_no INTEGER, recording_date DATE, round_label TEXT, data JSONB NOT NULL DEFAULT '{}'::jsonb,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(), updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_by UUID, archived_at TIMESTAMPTZ)
"""

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


def g(d, *path, default=None):
    for k in path:
        try:
            d = d[k]
        except (KeyError, IndexError, TypeError):
            return default
    return d


async def attempt(label, make):
    global FAIL
    try:
        return await make()
    except Exception as exc:  # noqa: BLE001
        FAIL += 1
        print(f"  FAIL {label}: raised {type(exc).__name__}: {str(exc)[:160]}")
        return None


# ── The stubbed grade ─────────────────────────────────────────────────────────
GRADE = str(uuid.uuid4())
R1, R2 = str(uuid.uuid4()), str(uuid.uuid4())
NAMES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot"]
TEAM = {n: (str(uuid.uuid4()), str(uuid.uuid4())) for n in NAMES}  # name -> (team id, club id)
RANK = {n: i + 1 for i, n in enumerate(NAMES)}
PIDS: dict[str, str] = {}


def pid(name):
    return PIDS.setdefault(name, str(uuid.uuid4()))


def team(n, home, players=None):
    tid, cid = TEAM[n]
    t = {"id": tid, "displayName": f"{n} 1st XI", "isHome": home,
         "owningOrganisation": {"id": cid, "name": f"{n} Cricket Club", "logoUrl": f"https://res.cloudinary.com/playhq/{n.lower()}.png"}}
    if players is not None:
        t["players"] = [{"participantId": pid(p), "displayName": p} for p in players]
    return t


def item(mid, rnd, rname, day, h, a, status, sid, result=""):
    return {"id": mid, "status": status, "statusId": sid, "resultText": result,
            "round": {"id": rnd, "name": rname},
            "matchSchedule": [{"matchDay": 1, "startDateTime": f"{day}T12:30:00+08:00"}],
            "venue": {"name": f"{h} Oval"}, "teams": [team(h, True), team(a, False)]}


M_AF, M_BE, M_CD, F_AB, F_CF, F_DE = (str(uuid.uuid4()) for _ in range(6))
GRADE_LIST = [
    item(M_AF, R1, "Round 1", "2026-11-14", "Alpha", "Foxtrot", "COMPLETED", 3, "Foxtrot 1st XI won by 2 wickets"),
    item(M_BE, R1, "Round 1", "2026-11-14", "Bravo", "Echo", "COMPLETED", 3, "Bravo 1st XI won by 3 runs"),
    item(M_CD, R1, "Round 1", "2026-11-14", "Charlie", "Delta", "ABANDONED", 4, "Abandoned"),
    item(F_AB, R2, "Round 2", "2026-11-21", "Alpha", "Bravo", "UPCOMING", 0),
    item(F_CF, R2, "Round 2", "2026-11-21", "Charlie", "Foxtrot", "UPCOMING", 0),
    item(F_DE, R2, "Round 2", "2026-11-21", "Delta", "Echo", "UPCOMING", 0),
]
CLIP = "https://highlights.example/clip.m3u8"


def bat(name, short, r, b, dtype, did, dtext="", clip=None):
    row = {"participantId": pid(name), "playerShortName": short, "runsScored": r, "ballsFaced": b,
           "foursScored": 0, "sixesScored": 0, "dismissalType": dtype, "dismissalTypeId": did, "dismissalText": dtext}
    if clip:
        row["highlight"] = {"highLightType": "WICKET", "highlightURL": clip}
    return row


def bowl(name, short, o, r, w, hat=0):
    return {"participantId": pid(name), "playerShortName": short, "oversBowled": o, "maidensBowled": 0,
            "runsConceded": r, "wicketsTaken": w, "hatTricks": hat}


def card(mid, h, a, h_inn, a_inn, home_won, result):
    ht, at = TEAM[h][0], TEAM[a][0]
    hp = [r["playerShortName"] for r in h_inn["batting"]]
    return {
        "id": mid, "grade": {"id": GRADE, "name": "1st Grade"}, "round": {"id": R1, "name": "Round 1"},
        "matchSummary": {"resultText": result, "teams": [
            {"id": ht, "isHome": True, "isWinner": home_won, "resultType": "WON" if home_won else "LOST"},
            {"id": at, "isHome": False, "isWinner": not home_won, "resultType": "LOST" if home_won else "WON"}]},
        "teams": [team(h, True, h_inn["names"]), team(a, False, a_inn["names"])],
        "innings": [
            {"battingTeamId": ht, "runsScored": h_inn["runs"], "numberOfWicketsFallen": h_inn["wk"],
             "batting": h_inn["batting"], "bowling": a_inn["bowls"], "fielding": a_inn["fielding"]},
            {"battingTeamId": at, "runsScored": a_inn["runs"], "numberOfWicketsFallen": a_inn["wk"],
             "batting": a_inn["batting"], "bowling": h_inn["bowls"], "fielding": h_inn["fielding"]},
        ],
    } if hp is not None else None


CARDS = {
    M_AF: card(M_AF, "Alpha", "Foxtrot",
               {"names": ["a one", "Al Two", "Al Bowler", "Al Dnb"], "runs": 180, "wk": 10,
                "batting": [bat("a one", "A One", 105, 80, "Caught", 2, "c: F Keep b: F Quick", CLIP),
                            bat("Al Two", "A Two", 20, 30, "Run Out", 6, "run out (F Field, F Keep)", CLIP),
                            bat("Al Dnb", "A Dnb", 0, 0, "Did Not Bat", 0, "did not bat")],
                "bowls": [bowl("Al Bowler", "A Bowler", 10, 40, 2)], "fielding": []},
               {"names": ["Fox Keep", "Fox Quick", "Fox Field", "Fox Bat"], "runs": 181, "wk": 8,
                "batting": [bat("Fox Bat", "F Bat", 60, 70, "Not Out", 1, "not out")],
                "bowls": [bowl("Fox Quick", "F Quick", 9.3, 20, 5, hat=1)],
                "fielding": [{"participantId": pid("Fox Keep"), "playerShortName": "F Keep", "totalCatches": 1,
                              "wicketKeeperCatches": 1, "stumpings": 0, "runOuts": 1},
                             {"participantId": pid("Fox Field"), "playerShortName": "F Field", "totalCatches": 0,
                              "wicketKeeperCatches": 0, "stumpings": 0, "runOuts": 1}]},
               False, "Foxtrot 1st XI won by 2 wickets"),
    M_BE: card(M_BE, "Bravo", "Echo",
               {"names": ["Bra Bat"], "runs": 150, "wk": 9, "batting": [bat("Bra Bat", "B Bat", 55, 60, "Bowled", 4, "b: E Bowl")],
                "bowls": [], "fielding": []},
               {"names": ["Ech Bowl"], "runs": 147, "wk": 10, "batting": [bat("Ech Bowl", "E Bowl", 10, 12, "Bowled", 4, "b: X")],
                "bowls": [bowl("Ech Bowl", "E Bowl", 10, 30, 4)], "fielding": []},
               True, "Bravo 1st XI won by 3 runs"),
}


async def fake_grade_matches(grade_id, force=False):
    return [dict(m) for m in GRADE_LIST] if grade_id == GRADE else []


async def fake_detail(match_id):
    for m in GRADE_LIST:
        if m["id"] == match_id:
            return {**m, "grade": {"id": GRADE, "name": "1st Grade"}}
    return None


async def fake_scorecard(match_id, *, force=False):
    return CARDS.get(match_id)


async def fake_ladder(grade_id):
    teams = [{"id": TEAM[n][0], "displayName": f"{n} 1st XI", "rank": RANK[n],
              "ladderData": [{"id": "played", "val": 1}, {"id": "competitionPoints", "val": 10 - RANK[n]}]}
             for n in NAMES]
    return {"ladders": [{"name": "Overall", "pools": [{"teams": teams}]}]}


gr.get_grade_matches = fake_grade_matches
gr.get_match_detail = fake_detail
gr.get_match_scorecard = fake_scorecard
gr.get_grade_ladder = fake_ladder
try:
    from app.services import association_crests as _crest_lib  # noqa: E402

    async def _no_fetch(url, *, client=None):
        return None  # the crest host is down: every crest falls back to its address
    _crest_lib.fetch_logo = _no_fetch
except Exception:  # noqa: BLE001
    pass

LINK = f"https://play.cricket.com.au/match/{M_BE}/bravo-v-echo"


class User:
    id = uuid.uuid4()


async def setup():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS workspace_kind TEXT"))
        for stmt in POD_DDL:
            await conn.execute(text(stmt))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS association_crests (
                workspace_id UUID NOT NULL, ca_org_id TEXT NOT NULL, name TEXT, src_url TEXT,
                original_png BYTEA, cleaned_png BYTEA, uploaded_png BYTEA,
                use_cleaned BOOLEAN NOT NULL DEFAULT TRUE, colour TEXT, colour2 TEXT,
                colour_by_hand BOOLEAN NOT NULL DEFAULT FALSE, version TEXT, uploaded_by UUID,
                uploaded_at TIMESTAMPTZ, created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                cut_style TEXT NOT NULL DEFAULT 'auto', clean_version INTEGER NOT NULL DEFAULT 1,
                PRIMARY KEY (workspace_id, ca_org_id))
        """))
        await conn.execute(text(OLD_DDL))
        for stmt in POD_DDL:  # the lifespan runs it on every boot: it must be idempotent
            await conn.execute(text(stmt))


async def make_org(db, name, kind):
    oid = uuid.uuid4()
    await db.execute(text(
        "INSERT INTO organisations (id, name, short_name, is_active, workspace_kind, module_overrides, tier, "
        "subscription_status) VALUES (:id, :n, :n, false, :k, '[\"socials\"]', 'good', 'active')"),
        {"id": oid, "n": name, "k": kind})
    await db.commit()
    return await db.get(Organisation, oid)


async def main():
    await setup()
    async with Session() as db:
        ws = await make_org(db, "Hills Association Socials", "association")
        ws2 = await make_org(db, "Coast Association Socials", "association")
        club = await make_org(db, "Alpha Cricket Club", None)
        user = User()

        print("\n[gate] association workspaces only")
        refused = None
        if pod is not None:
            try:
                await pod.require_association(club)
            except HTTPException as e:
                refused = e.status_code
        check("a club is refused the tracker (404)", refused, 404)
        allowed = await attempt("workspace passes the gate", lambda: pod.require_association(ws)) if pod else None
        check("a workspace passes the gate", allowed is ws)

        print("\n[pull] one match link reads the whole round")
        d = await attempt("pull", lambda: pod.pull(LINK, db, ws)) if pod else None
        check("kind is round", g(d, "kind"), "round")
        check("grade and round named", (g(d, "grade"), g(d, "round")), ("1st Grade", "Round 1"))
        res = g(d, "results", default=[])
        check("two results, the abandoned match is not one", len(res), 2)
        check("home team first, club short name in its own casing",
              [(r["home"], r["away"]) for r in res], [("Alpha", "Foxtrot"), ("Bravo", "Echo")])
        check("abandoned match listed as no result", [(m["home"], m["away"]) for m in g(d, "not_played", default=[])],
              [("Charlie", "Delta")])
        af = next((r for r in res if r["home"] == "Alpha"), {})
        check("winner read from the card (away side)", af.get("winner"), "away")
        check("scores read per side", (af.get("home_score"), af.get("away_score")), ("180", "8/181"))
        check("wicket margin counted for closeness", g(af, "margin", "closeness"), 2 * 12)
        be = next((r for r in res if r["home"] == "Bravo"), {})
        check("run margin counted for closeness", g(be, "margin", "closeness"), 3)
        check("upset: 6th beat 1st, read off the ladder", [(u["winner"], u["winner_rank"], u["loser_rank"]) for u in g(d, "upsets", default=[])],
              [("Foxtrot", 6, 1)])
        check("a lower-case name reads in title case", g(d, "batting", 0, "name"), "A One")
        check("best innings first, with a line", (g(d, "batting", 0, "runs"), g(d, "batting", 0, "line")), (105, "105 (80)"))
        check("did not bat is not an innings", any(b["name"] == "Al Dnb" for b in g(d, "batting", default=[])), False)
        check("best bowling first", g(d, "bowling", 0, "line"), "5/20 (9.3)")
        kinds = sorted(m["kind"] for m in g(d, "milestones", default=[]))
        check("hundred, fifty, five-for and hat-trick are milestones", kinds, ["fifty", "fifty", "five_for", "hat_trick", "hundred"])
        c0 = g(d, "catches", 0, default={})
        check("catcher named in full from the short name in the dismissal", c0.get("fielder"), "Fox Keep")
        check("keeper catch flagged from the fielding row", c0.get("keeper"), True)
        check("filmed catch carries its clip", c0.get("clip"), CLIP)
        ro = g(d, "run_outs", 0, default={})
        check("run out names both fielders in full", ro.get("fielders"), ["Fox Field", "Fox Keep"])
        check("filmed run out carries its clip", ro.get("clip"), CLIP)
        check("ladder in rank order", [r["team"] for r in g(d, "ladder", default=[])], NAMES)
        nxt = g(d, "next_round", default={})
        check("next round is round 2", (nxt.get("round"), len(nxt.get("fixtures") or [])), ("Round 2", 3))
        mor = g(nxt, "fixtures", g(nxt, "match_of_round"), default={})
        check("match of the round is 1st v 2nd", (mor.get("home"), mor.get("away")), ("Alpha", "Bravo"))
        # 105 runs is 105 points; five wickets is 5 x 20 = 100, plus nothing with the bat.
        check("player of the round ranked by match points", [(p["name"], p["points"]) for p in g(d, "performers", default=[])[:2]],
              [("A One", 105), ("Fox Quick", 100)])
        print("\n[posts] what the round posts read")
        alpha = TEAM["Alpha"][0]
        check("crest for every side in the grade", len(g(d, "crests", default={})), 6)
        check("a crest the library cannot fetch falls back to its address",
              g(d, "crests", alpha, "logo"), "https://res.cloudinary.com/playhq/alpha.png")
        check("innings carry their side's id (crest lookup)", g(d, "batting", 0, "team_id"), alpha)
        check("each side names its club (the crest library's key)", g(d, "clubs", alpha), {"id": TEAM["Alpha"][1], "name": "Alpha Cricket Club"})
        check("performers carry their side's id", g(d, "performers", 0, "team_id"), alpha)
        check("fixtures carry both sides' ids", (g(mor, "home_id"), g(mor, "away_id")), (alpha, TEAM["Bravo"][0]))
        bad = await attempt("pull with a PlayHQ link", lambda: pod.pull("https://www.playhq.com/x/game-centre/abcd1234", db, ws)) if pod else None
        check("a PlayHQ link says what to paste instead", g(bad, "kind"), "playhq")

        print("\n[rounds] create, save, carry over, scope, archive")
        r1 = await attempt("create round", lambda: pod.create_round(db, ws, user)) if pod else None
        rid = g(r1, "id")
        check("a round is created", bool(rid))
        data = {"competitions": [{"key": "north", "name": "North", "link": LINK, "pull": d}], "notes": "Foxtrot stun Alpha"}
        saved = await attempt("save", lambda: pod.save_round(
            rid, pod.RoundPatch(round_label="Round 1", round_date="2026-11-14", data=data), db, ws, user)) if rid else None
        check("round label saved", g(saved, "round_label"), "Round 1")
        check("the pull is kept on the round", len(g(saved, "data", "competitions", 0, "pull", "results", default=[])), 2)
        again = await attempt("save one field", lambda: pod.save_round(
            rid, pod.RoundPatch(round_date=None), db, ws, user)) if rid else None
        check("an explicit null clears it", (g(again, "round_date", default="x"), g(saved, "round_date")), (None, "2026-11-14"))
        check("an absent key is left alone", (g(again, "round_label"), g(again, "data", "notes")), ("Round 1", "Foxtrot stun Alpha"))
        r2 = await attempt("create next round", lambda: pod.create_round(db, ws, user)) if pod else None
        check("carries competition name and link", (g(r2, "data", "competitions", 0, "name"), g(r2, "data", "competitions", 0, "link")),
              ("North", LINK))
        check("does not carry last round's figures", g(r2, "data", "competitions", 0, "pull", default="absent"), "absent")
        check("does not carry notes", g(r2, "data", "notes", default="absent"), "absent")
        other = None
        if rid and pod:
            try:
                await pod.get_round(rid, db, ws2)
            except HTTPException as e:
                other = e.status_code
        check("another workspace cannot open this round", other, 404)
        lst = await attempt("list", lambda: pod.list_rounds(db, ws)) if pod else None
        check("list newest first", [r["id"] for r in g(lst, "rounds", default=[])], [g(r2, "id"), rid])
        await attempt("archive", lambda: pod.archive_round(rid, db, ws)) if rid else None
        lst = await attempt("list after archive", lambda: pod.list_rounds(db, ws)) if pod else None
        check("archived round leaves the list", [r["id"] for r in g(lst, "rounds", default=[])], [g(r2, "id")])
        kept = await db.scalar(text("SELECT count(*) FROM performance_rounds WHERE archived_at IS NOT NULL")) if pod else 0
        check("archived round row is kept, not deleted", kept, 1)

        print("\n[carry] the run sheet's saved episodes come across once")
        old_id = uuid.uuid4()
        await db.execute(text(
            "INSERT INTO podcast_episodes (id, organisation_id, episode_no, recording_date, round_label, data) "
            "VALUES (:id, :org, 3, '2026-11-08', 'Round 3', '{\"notes\": {\"story\": \"kept\"}}')"),
            {"id": old_id, "org": ws.id})
        await db.commit()
        for _ in range(2):  # every boot runs it again: twice must still be one row
            for stmt in POD_DDL:
                await db.execute(text(stmt))
            await db.commit()
        got = (await db.execute(text(
            "SELECT round_label, round_date, data->'notes'->>'story' FROM performance_rounds WHERE id = :id"),
            {"id": old_id})).all() if pod else []
        check("an episode becomes a round, once", [(r[0], str(r[1]), r[2]) for r in got], [("Round 3", "2026-11-08", "kept")])
        still = await db.scalar(text("SELECT count(*) FROM podcast_episodes"))
        check("the old table is left as it was", still, 1)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
