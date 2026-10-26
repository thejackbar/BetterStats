"""Verification: Past Lineups, a team's saved XIs going back in time, against a real Postgres.

Drives the SHIPPED route bodies `past_lineup_teams` and `past_lineups`, never a
re-implementation:

  * the team list holds only teams with a saved XI on a game that has been played,
    top team first; upcoming, cancelled and XI-less games and another club's games
    are not counted
  * a team's feed is newest first, players in batting order, captain and keeper flagged
  * each game says who came in and who dropped out against the game BEFORE it for the
    same team, including the oldest card of a page (read one game past the page)
  * paging: has_more / next_offset / total, and the first game on record has no baseline
  * a squad covering several teams is several teams: one side's feed never holds the other's
  * `fixture_id` means "this fixture's team" (an upcoming fixture works, another club's is a 404)
  * a game no squad claims is listed under no team; another club's lineup never appears

CONTROL MODE: run against the previous `routers/selection.py`. The routes are looked up
with getattr and every key is read with `.get`, so the control FAILS the checks that name
the missing feature instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_past_lineups.py
"""
from __future__ import annotations

import asyncio
import importlib
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import Fixture, FixtureLineup, Grade, Organisation, Player, Season, Team

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    async with engine.begin() as conn:
        for mod in ("selection_draft_ddl", "team_sides_ddl", "fixture_side_ddl", "fixture_pin_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
    import app.routers.selection as sel

    org, other_org, season, other_season = (uuid.uuid4() for _ in range(4))
    G = {n: uuid.uuid4() for n in ("Div1", "Alpha", "Bravo")}
    OG = uuid.uuid4()
    T = {n: uuid.uuid4() for n in ("Firsts", "Mac")}
    P = {n: uuid.uuid4() for n in ("p1", "p2", "p3", "p4", "p5", "x1")}
    today = date.today()
    d = lambda n: today + timedelta(days=n)  # noqa: E731
    FX: dict = {}

    async with Session() as db:
        db.add(Organisation(id=org, name="Gisborne CC", slug=f"gis-{org.hex[:8]}"))
        db.add(Organisation(id=other_org, name="Other CC", slug=f"oth-{other_org.hex[:8]}"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        db.add(Season(id=other_season, organisation_id=other_org, name="Summer", year=2026))
        await db.flush()
        for n, gid in G.items():
            db.add(Grade(id=gid, season_id=season, name=n, categories=["senior"]))
        db.add(Grade(id=OG, season_id=other_season, name="Div1", categories=["senior"]))
        await db.flush()
        db.add(Team(id=T["Firsts"], organisation_id=org, name="1st XI", sequence=1, grade_id=G["Div1"]))
        # One squad, two teams: Alpha is its 2nd XI, Bravo its 3rd.
        db.add(Team(id=T["Mac"], organisation_id=org, name="MACs", sequence=2, grade_id=G["Alpha"]))
        for n, pid in P.items():
            db.add(Player(id=pid, organisation_id=other_org if n == "x1" else org, name=n, is_player=True))
        await db.flush()
        await db.execute(text(
            "INSERT INTO team_sides (team_id, organisation_id, grade_key, grade_name, label, position) VALUES "
            "(:t, :o, 'alpha', 'Alpha', '2nd XI', 0), (:t, :o, 'bravo', 'Bravo', '3rd XI', 1)"
        ), {"t": T["Mac"], "o": org})

        def fx(key, grade, on, team=None, organisation=org, status="FINAL", opp=None, venue=None):
            f = Fixture(id=uuid.uuid4(), organisation_id=organisation, grade_id=grade, team_id=team,
                        source="grassroots", played_on=on, start_time="13:00", status=status,
                        opponent_name=opp or key, label=key, round=key, venue=venue)
            db.add(f)
            FX[key] = f.id
            return f

        # The 1st XI: four played games, plus the ones that must NOT count.
        fx("F1", G["Div1"], d(-35), T["Firsts"], venue="Home Oval")
        fx("F2", G["Div1"], d(-28), T["Firsts"])
        fx("F3", G["Div1"], d(-21), T["Firsts"])
        fx("F4", G["Div1"], d(-14), T["Firsts"])
        fx("F-up", G["Div1"], d(7), T["Firsts"], status="UPCOMING")          # not played yet
        fx("F-cancel", G["Div1"], d(-42), T["Firsts"], status="CANCELLED")   # cancelled
        fx("F-empty", G["Div1"], d(-49), T["Firsts"])                        # no XI saved
        fx("F-other", OG, d(-28), organisation=other_org)                    # another club, same grade name
        fx("F-orphan", None, d(-10))                                         # no squad, no grade
        # The squad's two teams, told apart by grade.
        fx("A1", G["Alpha"], d(-30), T["Mac"])
        fx("B1", G["Bravo"], d(-30), T["Mac"])      # same day as A1
        fx("B2", G["Bravo"], d(-23), T["Mac"])
        fx("A2", G["Alpha"], d(-16), T["Mac"])
        await db.flush()

        def xi(key, names, captain=None, keeper=None, organisation=org):
            for i, n in enumerate(names):
                db.add(FixtureLineup(fixture_id=FX[key], player_id=P[n], organisation_id=organisation,
                                     batting_order=i + 1, is_captain=(n == captain), is_wicket_keeper=(n == keeper)))

        xi("F1", ["p1", "p2", "p3"], captain="p1", keeper="p2")
        xi("F2", ["p1", "p2", "p4"])
        xi("F3", ["p1", "p2", "p4"])
        xi("F4", ["p2", "p4", "p5"])
        xi("F-up", ["p1", "p2", "p4"])
        xi("F-cancel", ["p5"])
        xi("F-other", ["x1"], organisation=other_org)
        xi("F-orphan", ["p5"])
        xi("A1", ["p1"])
        xi("B1", ["p3"])
        xi("B2", ["p3", "p4"])
        xi("A2", ["p1", "p5"])
        await db.commit()

    pid = lambda *ns: [str(P[n]) for n in ns]  # noqa: E731
    fid = lambda k: str(FX[k])  # noqa: E731

    async def club(db):
        return await db.get(Organisation, org)

    async def teams():
        fn = getattr(sel, "past_lineup_teams", None)
        if fn is None:
            return {}
        async with Session() as db:
            return await fn(db=db, club=await club(db), hide_juniors=False)

    async def feed(team=None, fixture_id=None, offset=0, limit=30):
        fn = getattr(sel, "past_lineups", None)
        if fn is None:
            return {}
        async with Session() as db:
            return await fn(team=team, fixture_id=fixture_id, offset=offset, limit=limit,
                            hide_juniors=False, db=db, club=await club(db))

    def ids(r):
        return [e.get("fixture_id") for e in (r.get("entries") or [])]

    def names(players):
        return sorted(p.get("player_id") for p in (players or []))

    print("\n# A. The team list")
    r = await teams()
    ts = r.get("teams") or []
    by_key = {t.get("key"): t for t in ts}
    FIRSTS, ALPHA, BRAVO = str(T["Firsts"]), f"{T['Mac']}:alpha", f"{T['Mac']}:bravo"
    check("the route exists and lists the club's three teams", sorted(by_key), sorted([FIRSTS, ALPHA, BRAVO]))
    check("top team first (1st XI, then the squad's 2nd and 3rd)", [t.get("key") for t in ts], [FIRSTS, ALPHA, BRAVO])
    check("a team counts only played games with a saved XI (4, not the upcoming, cancelled or empty one)",
          (by_key.get(FIRSTS) or {}).get("games"), 4)
    check("a squad's teams are counted apart (alpha 2, bravo 2)",
          ((by_key.get(ALPHA) or {}).get("games"), (by_key.get(BRAVO) or {}).get("games")), (2, 2))
    check("the squad's teams carry their own names", ((by_key.get(ALPHA) or {}).get("name"), (by_key.get(BRAVO) or {}).get("name")),
          ("2nd XI", "3rd XI"))
    check("the newest game is reported", (by_key.get(FIRSTS) or {}).get("last_played"), d(-14).isoformat())

    print("\n# B. A feed, newest first, with in and out")
    r = await feed(team=FIRSTS)
    check("games run newest first", ids(r), [fid("F4"), fid("F3"), fid("F2"), fid("F1")])
    check("the total is every played game with an XI", r.get("total"), 4)
    check("nothing more to load", (r.get("has_more"), r.get("next_offset")), (False, 4))
    check("the team is named", (r.get("team") or {}).get("name"), "1st XI")
    e = {x.get("fixture_id"): x for x in r.get("entries") or []}
    f4 = e.get(fid("F4")) or {}
    check("players come in batting order", [p.get("player_id") for p in f4.get("players") or []], pid("p2", "p4", "p5"))
    check("F4 vs F3: p5 in", names((f4.get("vs_previous") or {}).get("added")), pid("p5"))
    check("F4 vs F3: p1 out", names((f4.get("vs_previous") or {}).get("removed")), pid("p1"))
    check("the baseline names the older game", (f4.get("vs_previous") or {}).get("fixture_id"), fid("F3"))
    f3 = e.get(fid("F3")) or {}
    check("an unchanged side has nobody in or out",
          ((f3.get("vs_previous") or {}).get("added"), (f3.get("vs_previous") or {}).get("removed")), ([], []))
    check("(control for the check above) F2 vs F1 does show a change",
          (names((e.get(fid("F2")) or {}).get("vs_previous", {}).get("added")), names((e.get(fid("F2")) or {}).get("vs_previous", {}).get("removed"))),
          (pid("p4"), pid("p3")))
    f1 = e.get(fid("F1")) or {}
    check("the first game on record has no baseline", ("vs_previous" in f1, f1.get("vs_previous")), (True, None))
    check("captain and keeper are flagged",
          sorted((p.get("player_id"), p.get("is_captain"), p.get("is_wicket_keeper")) for p in f1.get("players") or [] if p.get("is_captain") or p.get("is_wicket_keeper")),
          sorted([(str(P["p1"]), True, False), (str(P["p2"]), False, True)]))
    check("the venue and round ride along", (f1.get("venue"), f1.get("round")), ("Home Oval", "F1"))

    print("\n# C. Paging")
    r = await feed(team=FIRSTS, limit=1)
    check("page 1 holds the newest game only", ids(r), [fid("F4")])
    check("...and says there is more", (r.get("has_more"), r.get("next_offset"), r.get("total")), (True, 1, 4))
    v = (r.get("entries") or [{}])[0].get("vs_previous") or {}
    check("the only card on the page still has its in/out (reads a game past the page)",
          (names(v.get("added")), names(v.get("removed"))), (pid("p5"), pid("p1")))
    r = await feed(team=FIRSTS, offset=1, limit=2)
    check("page 2 continues where page 1 stopped", ids(r), [fid("F3"), fid("F2")])
    v = (r.get("entries") or [{}, {}])[1].get("vs_previous") or {}
    check("the oldest card of a middle page compares to the game on the next page",
          (v.get("fixture_id"), names(v.get("added")), names(v.get("removed"))), (fid("F1"), pid("p4"), pid("p3")))
    r = await feed(team=FIRSTS, offset=3, limit=2)
    check("the last page holds the first game ever, with nothing more", (ids(r), r.get("has_more")), ([fid("F1")], False))
    check("...and it has no baseline", (r.get("entries") or [{}])[0].get("vs_previous", "absent"), None)
    r = await feed(team=FIRSTS, offset=40, limit=5)
    check("paging past the end is empty, not an error", (ids(r), r.get("has_more")), ([], False))

    print("\n# D. A squad with several teams")
    r = await feed(team=ALPHA)
    check("alpha holds only its own games, newest first", ids(r), [fid("A2"), fid("A1")])
    av = ((r.get("entries") or [{}])[0].get("vs_previous") or {})
    check("alpha: A2 vs A1 is p5 in, nobody out", (names(av.get("added")), av.get("removed")), (pid("p5"), []))
    r = await feed(team=BRAVO)
    check("bravo holds only its own games, though A1 and B1 share a day", ids(r), [fid("B2"), fid("B1")])
    bv = ((r.get("entries") or [{}])[0].get("vs_previous") or {})
    check("bravo: B2 vs B1 is p4 in", names(bv.get("added")), pid("p4"))
    check("(control) bravo never holds alpha's p5", any(str(P["p5"]) in names(x.get("players")) for x in r.get("entries") or []), False)

    print("\n# E. By fixture")
    r = await feed(fixture_id=fid("F-up"))
    check("an upcoming fixture reads its team's past sides", ids(r), [fid("F4"), fid("F3"), fid("F2"), fid("F1")])
    check("...and the upcoming game itself is not among them", fid("F-up") in ids(r), False)
    r = await feed(fixture_id=fid("B2"))
    check("a fixture of a multi-team squad reads its own team", (r.get("team") or {}).get("key"), BRAVO)
    r = await feed(fixture_id=fid("F-orphan"))
    check("a game no squad claims has no team to look back at", ((r.get("team")), ids(r)), (None, []))
    code = None
    try:
        await feed(fixture_id=fid("F-other"))
    except HTTPException as ex:
        code = ex.status_code
    check("another club's fixture is a 404", code, 404)
    r = await feed(team="not-a-team")
    check("an unknown team key is empty, not an error", (ids(r), r.get("total")), ([], 0))
    check("(control) a feed with a team returns something", bool(ids(await feed(team=FIRSTS))), True)

    print("\n# F. Nothing leaks")
    seen = set()
    for k in (FIRSTS, ALPHA, BRAVO):
        for x in (await feed(team=k)).get("entries") or []:
            seen.update(p.get("player_id") for p in x.get("players") or [])
            seen.update(p.get("player_id") for p in (x.get("vs_previous") or {}).get("added") or [])
            seen.update(p.get("player_id") for p in (x.get("vs_previous") or {}).get("removed") or [])
    check("another club's player is in no feed", str(P["x1"]) in seen, False)
    check("(control) the club's own players are", str(P["p1"]) in seen, True)
    all_ids = set()
    for k in (FIRSTS, ALPHA, BRAVO):
        all_ids.update(ids(await feed(team=k)))
    check("another club's game is in no feed", fid("F-other") in all_ids, False)
    check("the cancelled and the XI-less games are in none", (fid("F-cancel") in all_ids, fid("F-empty") in all_ids), (False, False))

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    for f in base.FAILURES:
        print("  -", f)
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
