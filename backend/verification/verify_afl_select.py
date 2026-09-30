"""Football BetterSelect, against a real Postgres, through the real AFL boot
path and HTTP stack.

Sides seeded from PlayHQ's teams, the draw turned into fixtures, squads filed
from who played where, availability, the field and bench, and the league's
rules: team size, a concussion stand-down, an age limit, finals qualification
and the cap on games in a higher side.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/afl_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_afl_select.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")
os.environ.setdefault("SPORT", "afl")

from sqlalchemy import text  # noqa: E402

PASS = FAIL = 0


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


FIELD = ["LBP", "FB", "RBP", "LHB", "CHB", "RHB", "LW", "C", "RW",
         "LHF", "CHF", "RHF", "LFP", "FF", "RFP", "RUCK", "RR", "ROV"]


async def main():
    import httpx
    from app.models.db import (ClubMembership, Game, Grade, Organisation, Player, Season, User,
                               engine, async_session_maker)
    from app.models.afl import AflGameDetails, AflPlayerGameLine, AflTeam
    from app.afl_main import app, lifespan
    from app.routers.auth import COOKIE_NAME, create_session_token

    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    async with lifespan(None):
        pass

    has_route = any("/afl-select" in getattr(r, "path", "") for r in app.routes)
    check("football BetterSelect is mounted", has_route)
    if not has_route:
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    today = date.today()
    org, other, u, u2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    season, g_sen, g_res = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    oth_season, oth_grade = uuid.uuid4(), uuid.uuid4()
    names = ["Ruck, Ray", "Mid, Max", "Back, Bo", "Fwd, Fin", "Wing, Will", "Young, Yan", "Old, Olly",
             "Res, Rex", "Lapsed, Len"] + [f"Squad, S{i:02d}" for i in range(20)]
    P = {n: uuid.uuid4() for n in names}
    foreign = uuid.uuid4()
    past = [today - timedelta(days=d) for d in (21, 14, 7)]
    up = today + timedelta(days=5)
    final_day = today + timedelta(days=40)
    gp = [uuid.uuid4() for _ in past]
    g_up, g_up_res, g_final, g_res_final = (uuid.uuid4() for _ in range(4))
    g_old = uuid.uuid4()
    oth_game = uuid.uuid4()

    async with async_session_maker() as db:
        db.add_all([
            Organisation(id=org, name="Curtin Uni Wesley", slug="cuw", is_active=True,
                         module_overrides=["select"], subscription_status="active"),
            Organisation(id=other, name="Hampton", slug="hh", is_active=True, subscription_status="active"),
            User(id=u, username="coach", email="c@x.io", password_hash="x"),
            User(id=u2, username="hcoach", email="h@x.io", password_hash="x"),
            Season(id=season, organisation_id=org, name="VAFA 2026", year=today.year),
            Season(id=oth_season, organisation_id=other, name="VAFA 2026", year=today.year),
        ])
        await db.flush()
        db.add_all([
            ClubMembership(user_id=u, club_id=org, role="club_admin", is_primary_admin=True),
            ClubMembership(user_id=u2, club_id=other, role="club_admin", is_primary_admin=True),
            Grade(id=g_sen, season_id=season, name="Premier C Seniors"),
            Grade(id=g_res, season_id=season, name="Premier C Reserves"),
            Grade(id=oth_grade, season_id=oth_season, name="Seniors"),
        ])
        await db.flush()
        for n, pid in P.items():
            dob = None
            if n == "Young, Yan":
                dob = date(today.year - 18, 6, 1)   # 17 at 1 Jan, 18 by mid-year
            if n == "Old, Olly":
                dob = date(today.year - 20, 6, 1)   # 19 at 1 Jan
            db.add(Player(id=pid, organisation_id=org, name=n, date_of_birth=dob,
                          phone="0400 000 111" if n == "Mid, Max" else None,
                          skill_positions=["RUCK"] if n.startswith("Ruck") else ["MID"]))
        db.add(Player(id=foreign, organisation_id=other, name="Other, Oscar"))
        db.add_all([
            AflTeam(id=uuid.uuid4(), organisation_id=org, season_id=season, grade_id=g_res,
                    playhq_id="t-res", name="Curtin Uni Wesley Reserves"),
            AflTeam(id=uuid.uuid4(), organisation_id=org, season_id=season, grade_id=g_sen,
                    playhq_id="t-sen", name="Curtin Uni Wesley Seniors"),
        ])
        await db.flush()

        details = []

        def game(gid, grade, day, final=False, status="FINAL", rnd="Round 1", side="HOME"):
            db.add(Game(id=gid, grade_id=grade, played_at=day, is_final=final,
                        home_team="Curtin Uni Wesley Seniors" if grade == g_sen else "Curtin Uni Wesley Reserves",
                        away_team="Old Trinity", opp_club_name="Old Trinity", venue="Wesley Oval"))
            details.append(AflGameDetails(game_id=gid, playhq_id=f"phq-{gid}", status=status, our_side=side,
                                  round_name=rnd, start_time="14:00:00",
                                  synced_at=datetime.now() if status == "FINAL" else None))

        for i, (gid, day) in enumerate(zip(gp, past)):
            game(gid, g_sen, day, rnd=f"Round {i + 1}")
        game(g_up, g_sen, up, status="UPCOMING", rnd="Round 9")
        game(g_up_res, g_res, up, status="UPCOMING", rnd="Round 9")
        game(g_final, g_sen, final_day, final=True, status="UPCOMING", rnd="Grand Final")
        game(g_res_final, g_res, final_day, final=True, status="UPCOMING", rnd="Grand Final")
        game(g_old, g_res, today - timedelta(days=900), rnd="Round 3")
        await db.flush()
        db.add_all(details)
        await db.flush()

        def line(gid, pid, goals=0, bog=None, side="HOME", name="x"):
            db.add(AflPlayerGameLine(id=uuid.uuid4(), game_id=gid, side=side, player_id=pid, name=name,
                                     playhq_participant_id=str(uuid.uuid4()), goals=goals, bog_ranking=bog))
        # Ruck: 3 senior games, 4 goals, one best on ground. Mid: 2 senior games.
        for gid in gp:
            line(gid, P["Ruck, Ray"], goals=1)
        line(gp[0], P["Ruck, Ray"], goals=1, bog=1, side="AWAY")  # the opposition's side of the game
        for gid in gp[:2]:
            line(gid, P["Mid, Max"])
        # The opposition's player on OUR game's other side must never count.
        line(gp[2], P["Res, Rex"], side="AWAY")
        line(g_old, P["Lapsed, Len"])
        await db.commit()

    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    c = httpx.AsyncClient(transport=transport, base_url="http://t",
                          cookies={COOKIE_NAME: create_session_token(str(u))})
    h = httpx.AsyncClient(transport=transport, base_url="http://t",
                          cookies={COOKIE_NAME: create_session_token(str(u2))})

    def J(r):
        return r.json() if r.status_code < 300 else {}

    print("\n── The module gate ──")
    check("a club without BetterSelect is refused", (await h.get("/afl-select/teams")).status_code, 402)

    print("\n── Sides from PlayHQ ──")
    r = J(await c.post("/afl-select/teams/seed"))
    check("two sides are created", r.get("created"), 2)
    teams = J(await c.get("/afl-select/teams"))
    check("the seniors come first, whatever order PlayHQ gave them",
          [t["name"] for t in teams], ["Curtin Uni Wesley Seniors", "Curtin Uni Wesley Reserves"])
    check("a second seed creates nothing", J(await c.post("/afl-select/teams/seed")).get("created"), 0)
    sen_id, res_id = teams[0]["id"], teams[1]["id"]

    print("\n── The draw becomes fixtures ──")
    r = J(await c.post("/afl-select/fixtures/sync"))
    check("the upcoming games and last fortnight become fixtures", r.get("fixtures"), 6)
    fx = J(await c.get("/afl-select/fixtures"))
    up_rows = fx.get("fixtures", [])
    check("four fixtures still to come", len(up_rows), 4)
    sen_up = next((f for f in up_rows if f["id"] == str(g_up)), {})
    check("a fixture keeps the game's own id", bool(sen_up))
    check("  ... names the side that plays it", sen_up.get("team_id"), sen_id)
    check("  ... the round and time from PlayHQ", (sen_up.get("round"), sen_up.get("start_time")), ("Round 9", "14:00"))
    check("  ... home, v the right club", (sen_up.get("home_away"), sen_up.get("opponent_name")), ("HOME", "Old Trinity"))
    gf = next((f for f in up_rows if f["id"] == str(g_final)), {})
    check("a grand final is marked as a final", gf.get("is_final"), True)
    r2 = J(await c.post("/afl-select/fixtures/sync"))
    check("a second sync creates nothing", r2.get("created"), 0)

    print("\n── Squads ──")
    r = J(await c.post("/afl-select/teams/auto-assign"))
    check("players are filed under the side they played most for", r.get("assigned"), 3)
    sq = {p["name"]: p for p in J(await c.get("/afl-select/squads")).get("players", [])}
    check("the ruck is in the seniors", sq["Ruck, Ray"]["squad_id"], sen_id)
    check("a player seen only on the opposition's side is filed nowhere", sq["Res, Rex"]["squad_id"], None)
    check("a player last seen years ago reads as lapsed", sq["Lapsed, Len"]["lapsed"], True)
    check("  ... and is filed where he played", sq["Lapsed, Len"]["squad_id"], res_id)
    r = await c.put(f"/afl-select/squads/{P['Res, Rex']}", json={"team_id": res_id})
    check("a player can be put in a squad by hand", r.status_code, 200)
    check("another club's player can't", (await c.put(f"/afl-select/squads/{foreign}", json={"team_id": res_id})).status_code, 404)

    print("\n── Availability ──")
    r = await c.post("/afl-select/availability", json={"player_id": str(P["Wing, Will"]), "date": up.isoformat(), "status": "UNAVAILABLE"})
    check("an answer is recorded", r.status_code, 200)
    r = await c.post("/afl-select/availability/periods", json={"player_id": str(P["Back, Bo"]),
                     "start_date": (up - timedelta(days=2)).isoformat(), "status": "UNAVAILABLE", "reason": "Hamstring"})
    check("a period is recorded", r.status_code, 200)
    av = J(await c.get("/afl-select/availability"))
    check("the matrix offers each match date once", [d["date"] for d in av.get("dates", [])],
          sorted({up.isoformat(), final_day.isoformat()}))
    check("the answer is on the matrix", av["availability"].get(str(P["Wing, Will"]), {}).get(up.isoformat(), {}).get("status"), "UNAVAILABLE")
    check("the period covers the date", av["availability"].get(str(P["Back, Bo"]), {}).get(up.isoformat(), {}).get("source"), "period")

    print("\n── The board ──")
    sel = J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))
    form = sel.get("formation", [])
    check("six lines", [l["key"] for l in form], ["B", "HB", "C", "HF", "F", "FOL"])
    check("eighteen on the ground", sum(len(l["slots"]) for l in form), 18)
    check("a senior side's bench and emergencies", sel.get("team_size"), {"field": 18, "bench": 10, "emergencies": 3})
    pool = {p["name"]: p for p in sel.get("players", [])}
    ray = pool["Ruck, Ray"]
    check("form counts our side only: 3 games", ray["games"], 3)
    check("  ... 3 goals, not the opposition line's", ray["goals"], 3)
    check("  ... and no best on ground from the other side", ray["best_on_ground"], 0)
    check("positions are football's", ray["positions"], ["RUCK"])
    check("an unavailable player reads so", pool["Wing, Will"]["availability"], "UNAVAILABLE")
    check("a period reads so too", pool["Back, Bo"]["availability"], "UNAVAILABLE")

    squad = [P[n] for n in names if n.startswith("Squad")]
    side = [{"player_id": str(squad[i]), "slot": s} for i, s in enumerate(FIELD)]
    side[15] = {"player_id": str(P["Ruck, Ray"]), "slot": "RUCK", "is_captain": True}
    side += [{"player_id": str(squad[18]), "slot": "INT", "sort_order": 1},
             {"player_id": str(squad[19]), "slot": "INT", "sort_order": 2},
             {"player_id": str(P["Mid, Max"]), "slot": "EMG", "sort_order": 1}]
    r = await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": side})
    check("eighteen, two on the bench and an emergency save", r.status_code, 200)
    sel = J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))
    check("the side comes back", len(sel.get("lineup", [])), 21)
    check("  ... with its captain", next((x for x in sel["lineup"] if x["is_captain"]), {}).get("slot"), "RUCK")

    bad = [dict(x) for x in side]
    bad[1] = {"player_id": bad[1]["player_id"], "slot": "LBP"}
    check("two players at one position is refused", (await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": bad})).status_code, 422)
    bad = [dict(x) for x in side] + [{"player_id": str(foreign), "slot": "INT"}]
    check("another club's player is refused", (await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": bad})).status_code, 422)
    bad = [dict(x) for x in side]
    bad[0] = {**bad[0], "is_captain": True}
    check("two captains is refused", (await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": bad})).status_code, 422)
    check("another club can't read our fixture", (await h.get(f"/afl-select/fixtures/{g_up}/selection")).status_code, 402)

    # The reserves play the same day: naming the ruck there is a clash.
    r = await c.put(f"/afl-select/fixtures/{g_up_res}/lineup", json={"items": [{"player_id": str(P["Ruck, Ray"]), "slot": "FB"}]})
    check("a part side saves", r.status_code, 200)
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_up}/selection")).get("players", [])}
    check("the seniors' board says he's named elsewhere that day", pool["Ruck, Ray"]["clash"], "Curtin Uni Wesley Reserves")

    ts = J(await c.get(f"/afl-select/fixtures/{g_up}/team-sheet")).get("text", "")
    check("the team sheet reads the football way",
          all(k in ts for k in ("\nB: ", "\nHB: ", "\nC: ", "\nHF: ", "\nF: ", "\nFoll: ", "\nI/C: ", "\nEmg: ")), True, )
    check("  ... with the captain marked", "Ruck, Ray (c)" in ts)
    prev = J(await c.get(f"/afl-select/fixtures/{g_final}/previous")).get("lineup", [])
    check("the grand final starts from last week's side", len(prev), 21)

    print("\n── Rules ──")
    r = J(await c.post("/afl-select/rules/starter"))
    check("the starter adds team size and the concussion stand-down", sorted(r.get("added", [])), ["concussion", "team_size"])
    check("pressing it twice adds nothing", J(await c.post("/afl-select/rules/starter")).get("added"), [])
    rules = {x["kind"]: x for x in J(await c.get("/afl-select/rules")).get("rules", [])}
    ts_id, con_id = rules["team_size"]["id"], rules["concussion"]["id"]
    check("the stand-down is AFL's 21 days", rules["concussion"]["config"], {"days": 21})

    await c.patch(f"/afl-select/rules/{ts_id}", json={"config": {"field": 16, "bench": 1, "emergencies": 2},
                                                        "scope": {"grade_names": ["Premier C Reserves"]}})
    rsel = J(await c.get(f"/afl-select/fixtures/{g_up_res}/selection"))
    check("a 16-a-side grade drops the wings", sum(len(l["slots"]) for l in rsel.get("formation", [])), 16)
    check("  ... and has no LW slot", "LW" in [s["slot"] for l in rsel["formation"] for s in l["slots"]], False)
    check("the seniors are still 18", sum(len(l["slots"]) for l in J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))["formation"]), 18)
    r = await c.put(f"/afl-select/fixtures/{g_up_res}/lineup", json={"items": [{"player_id": str(P["Res, Rex"]), "slot": "LW"}]})
    check("a wing on a 16-a-side ground is refused", r.status_code, 422)
    r = await c.put(f"/afl-select/fixtures/{g_up_res}/lineup", json={"items": [
        {"player_id": str(P["Res, Rex"]), "slot": "INT"}, {"player_id": str(P["Old, Olly"]), "slot": "INT"}]})
    check("two on a one-man bench is refused", r.status_code, 422)

    r = await c.post(f"/afl-select/rules/{con_id}/players", json={"player_id": str(squad[0]), "mode": "incident",
                     "incident_date": (up - timedelta(days=10)).isoformat()})
    check("a concussion is recorded", r.status_code, 200)
    pool = {p["id"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))["players"]}
    fl = pool[str(squad[0])]["flags"]
    check("he's stood down for this week", [f["kind"] for f in fl], ["concussion"])
    check("  ... and it blocks", fl[0]["severity"] if fl else None, "block")
    r = await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": side})
    check("the save is refused while he's stood down", r.status_code, 422)
    check("  ... saying why", "Squad, S00" in str(r.json().get("detail")), True)
    pool = {p["id"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_final}/selection"))["players"]}
    check("he's clear by the grand final", pool[str(squad[0])]["flags"], [])
    await c.post(f"/afl-select/rules/{con_id}/players", json={"player_id": str(squad[0]), "mode": "permit", "note": "Cleared by doctor"})
    check("a medical clearance lets the side save", (await c.put(f"/afl-select/fixtures/{g_up}/lineup", json={"items": side})).status_code, 200)

    r = J(await c.post("/afl-select/rules", json={"kind": "age", "config": {"under_age": 19, "basis": "jan1"}, "severity": "warn"}))
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))["players"]}
    check("19 at 1 January is over an under-19 limit", [f["kind"] for f in pool["Old, Olly"]["flags"]], ["age"])
    check("17 at 1 January is inside it", pool["Young, Yan"]["flags"], [])
    check("no date of birth says nothing", pool["Wing, Will"]["flags"], [])
    await c.delete(f"/afl-select/rules/{r['id']}")

    await c.post("/afl-select/rules", json={"kind": "finals_qualification", "config": {"min_games": 3}, "severity": "block"})
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_final}/selection"))["players"]}
    check("two games isn't enough for finals", [f["kind"] for f in pool["Mid, Max"]["flags"]], ["finals_qualification"])
    check("three is", pool["Ruck, Ray"]["flags"], [])
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_up}/selection"))["players"]}
    check("the rule says nothing before September", pool["Mid, Max"]["flags"], [])

    await c.post("/afl-select/rules", json={"kind": "higher_grade_limit", "config": {"max_games": 2}, "severity": "block"})
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_res_final}/selection"))["players"]}
    check("three senior games rules him out of the reserves' final", "higher_grade_limit" in [f["kind"] for f in pool["Ruck, Ray"]["flags"]], True)
    check("two senior games doesn't", "higher_grade_limit" in [f["kind"] for f in pool["Mid, Max"]["flags"]], False)
    pool = {p["name"]: p for p in J(await c.get(f"/afl-select/fixtures/{g_final}/selection"))["players"]}
    check("the seniors' own final isn't lower than anything", "higher_grade_limit" in [f["kind"] for f in pool["Ruck, Ray"]["flags"]], False)

    print("\n── The player's own link ──")
    s = J(await c.post("/afl-select/availability/self-service", json={"enabled": True}))
    check("turning it on mints a link", bool(s.get("token")))
    land = (await httpx.AsyncClient(transport=transport, base_url="http://t").get(f"/public/availability/{s.get('token')}")).json()
    listed = {p.get("name") or p.get("display_name") for p in land.get("players", [])}
    check("the link lists the club's current players", "Mid, Max" in listed)
    check("  ... but not one who hasn't played for years", "Lapsed, Len" in listed, False)

    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        sys.exit(1)


asyncio.run(main())
