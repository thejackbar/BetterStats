"""Verification: a squad's availability is read against ITS next game.

The reported behaviour (BetterSelect feedback, Oct 2026): availability typed on
the Squads board for the Saturday 3s landed on the club's next game, a midweek
T20, because the board used the club's first upcoming date for every column.

Two layers:

  1. The rule itself (`services/squad_next_game.py`, pure, no database).
  2. The shipped `GET /availability/matrix` route body, when DATABASE_URL points
     at a real Postgres (skipped, and said so, when it does not).

Each "squad reads its own game" check is paired with the OLD behaviour run as a
control (`club_first_date`), which must give the reported wrong answer; a check
that passes against the broken code is not a check.

Run:  python verification/verify_squad_next_game.py
      DATABASE_URL=postgresql+asyncpg://... python verification/verify_squad_next_game.py
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

PASS = FAIL = 0
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL {name}  {detail}")


def load_service():
    spec = importlib.util.spec_from_file_location("squad_next_game", ROOT / "app/services/squad_next_game.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def club_first_date(by_date: dict) -> str | None:
    """The behaviour that was reported: every squad reads the club's first date."""
    return sorted(by_date)[0] if by_date else None


def fx(fid, team=None, grade=None, opp=None, role="single", home_away="HOME", label=None):
    return {"id": fid, "label": label, "opponent_name": opp, "home_away": home_away,
            "role": role, "two_day": role != "single", "team_id": team, "grade_id": grade}


def pure_checks() -> None:
    print("pure rule")
    svc = load_service()
    t20, thirds, firsts, bare = "t-t20", "t-3s", "t-1s", "t-bare"
    g_t20, g_3, g_1 = "g-t20", "g-3", "g-1"
    tue = "2026-10-13"
    sat = "2026-10-17"
    sun = "2026-10-18"
    by_date = {
        tue: [fx("f-t20", team=t20, grade=g_t20, opp="Jarrah T20")],
        sat: [fx("f-1", team=None, grade=g_1, opp="Willetton 1s"),
              fx("f-3", team=None, grade=g_3, opp="Willetton 3s")],
        sun: [fx("f-1-day2", team=None, grade=g_1, role="day2")],
    }
    teams = [(t20, g_t20), (thirds, g_3), (firsts, g_1), (bare, None)]
    out = svc.squad_next_games(by_date, teams)

    # Control: the old rule gives the 3s the T20's Tuesday. That is the report.
    check("control: old rule puts the 3s on the T20's date", club_first_date(by_date) == tue)
    check("3s read their own Saturday, not the T20's Tuesday", out[thirds]["date"] == sat, str(out[thirds]))
    check("3s fixture is the 3s game", out[thirds]["fixture_id"] == "f-3" and out[thirds]["opponent_name"] == "Willetton 3s")
    check("T20 squad still reads the T20", out[t20]["date"] == tue and out[t20]["scope"] == "squad")
    check("1s read Saturday (day 1), not the day-2 Sunday", out[firsts]["date"] == sat)
    check("a squad with no grade reads the club's first date, labelled club",
          out[bare]["date"] == tue and out[bare]["scope"] == "club")

    # The Sunday after the Saturday game: the Saturday fixtures are gone, so the
    # 3s' next game is the following Saturday, not whatever the club plays next.
    sat2 = "2026-10-24"
    after = {
        "2026-10-19": [fx("f-t20-2", team=t20, grade=g_t20, opp="Jarrah T20")],
        sat2: [fx("f-3-2", team=None, grade=g_3, opp="Kenwick 3s")],
    }
    out2 = svc.squad_next_games(after, teams)
    check("control (Sunday): old rule is again the T20's date", club_first_date(after) == "2026-10-19")
    check("Sunday after: 3s default to their next Saturday", out2[thirds]["date"] == sat2, str(out2[thirds]))

    # A grade with nothing upcoming says so: no date, never another grade's game.
    only_t20 = {tue: [fx("f-t20", team=t20, grade=g_t20)]}
    out3 = svc.squad_next_games(only_t20, teams)
    check("graded squad with no upcoming game gets no date", out3[thirds]["date"] is None and out3[thirds]["scope"] == "none", str(out3[thirds]))
    check("...while the control would have given it the T20's date", club_first_date(only_t20) == tue)

    # A fixture that names another squad is that squad's, even in the same grade.
    two = {sat: [fx("f-a", team="t-a", grade=g_3, opp="A"), fx("f-b", team="t-b", grade=g_3, opp="B")]}
    out4 = svc.squad_next_games(two, [("t-a", g_3), ("t-b", g_3), ("t-c", g_3)])
    check("two squads in one grade each take their own fixture",
          out4["t-a"]["fixture_id"] == "f-a" and out4["t-b"]["fixture_id"] == "f-b")
    check("a third squad in the grade takes neither named fixture", out4["t-c"]["scope"] == "none")

    # An empty fixture list is not a crash.
    out5 = svc.squad_next_games({}, teams)
    check("no upcoming fixtures at all: every squad has no date",
          all(v["date"] is None for v in out5.values()))
    check("shape is stable (every key present)",
          all(set(v) == {"date", "fixture_id", "opponent_name", "label", "home_away", "scope"} for v in out.values()))


async def route_checks(db_url: str) -> None:
    print("matrix route (real Postgres)")
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.models.db import Base, Organisation, Team, Grade, Season, Fixture
    from app.routers import availability as av

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    from sqlalchemy import text
    from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # The matrix reads the club's association rules: a raw-SQL lifespan
        # table create_all never built. Lifted from the shared DDL, not stubbed.
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        # Lifespan-only tables the grade classification (junior hiding, women's
        # side) reads through grade_alias_map; copied from the lifespan.
        for stmt in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(stmt))

    org_id, season_id = uuid.uuid4(), uuid.uuid4()
    g_t20, g_3 = uuid.uuid4(), uuid.uuid4()
    t_t20, t_3 = uuid.uuid4(), uuid.uuid4()
    today = date.today()
    tue, sat = today + timedelta(days=2), today + timedelta(days=6)
    async with Session() as s:
        s.add(Organisation(id=org_id, name=f"SquadNext {org_id.hex[:6]}", slug=f"sn-{org_id.hex[:8]}"))
        await s.flush()
        s.add(Season(id=season_id, organisation_id=org_id, name="2026/27"))
        await s.flush()
        s.add(Grade(id=g_t20, season_id=season_id, name="T20"))
        s.add(Grade(id=g_3, season_id=season_id, name="Saturday 3s"))
        await s.flush()
        s.add(Team(id=t_t20, organisation_id=org_id, name="T20", grade_id=g_t20))
        s.add(Team(id=t_3, organisation_id=org_id, name="3rd XI", grade_id=g_3))
        await s.flush()
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=g_t20, team_id=t_t20,
                      source="manual", played_on=tue, opponent_name="Jarrah T20"))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=g_3, team_id=None,
                      source="manual", played_on=sat, opponent_name="Willetton 3s"))
        await s.commit()
        club = await s.get(Organisation, org_id)
        body = await av.availability_matrix(db=s, club=club)

    check("matrix still lists the club's dates, first is the T20's",
          [d["date"] for d in body["dates"]][:1] == [tue.isoformat()])
    sn = body.get("squad_next") or {}
    check("matrix carries squad_next", bool(sn), str(sn))
    check("route: 3rd XI reads Saturday", (sn.get(str(t_3)) or {}).get("date") == sat.isoformat(), str(sn.get(str(t_3))))
    check("route: T20 squad reads Tuesday", (sn.get(str(t_t20)) or {}).get("date") == tue.isoformat())
    check("route: control, old rule (dates[0]) gives the 3rd XI Tuesday",
          body["dates"][0]["date"] == tue.isoformat())
    async with Session() as s:
        plain = await av.upcoming_fixtures_by_date(s, org_id)
        try:
            scoped = await av.upcoming_fixtures_by_date(s, org_id, with_scope=True)
        except TypeError:   # the previous code has no such argument: report, don't crash
            scoped = {}
    flat_plain = [f for fs in plain.values() for f in fs]
    flat_scoped = [f for fs in scoped.values() for f in fs]
    check("self-service shape has no team_id/grade_id", all("team_id" not in f and "grade_id" not in f for f in flat_plain))
    check("scoped shape has them", bool(flat_scoped) and all("team_id" in f and "grade_id" in f for f in flat_scoped))

    async with Session() as s:
        from sqlalchemy import delete
        await s.execute(delete(Fixture).where(Fixture.organisation_id == org_id))
        await s.execute(delete(Team).where(Team.organisation_id == org_id))
        await s.execute(delete(Grade).where(Grade.season_id == season_id))
        await s.execute(delete(Season).where(Season.id == season_id))
        await s.execute(delete(Organisation).where(Organisation.id == org_id))
        await s.commit()
    await engine.dispose()


def started_pure_checks() -> None:
    print("started games drop out (pure)")
    from datetime import datetime
    svc = load_service()
    day = date(2026, 10, 17)
    at = lambda h, m=0: datetime(2026, 10, 17, h, m)
    f = svc.fixture_has_started
    check("before the start time the game stays", f("UPCOMING", day, "13:00", at(12, 59)) is False)
    check("at the start time it goes", f("UPCOMING", day, "13:00", at(13, 0)) is True)
    check("after the start time it stays gone", f("UPCOMING", day, "13:00", at(17, 30)) is True)
    check("an earlier game goes while a later one the same day stays",
          f("UPCOMING", day, "09:30", at(11)) is True and f("UPCOMING", day, "14:00", at(11)) is False)
    check("start time with seconds is read", f("UPCOMING", day, "13:00:00", at(13, 5)) is True)
    check("no start time: kept for the whole date", f("UPCOMING", day, None, at(23, 59)) is False)
    check("an unreadable start time is kept, not guessed", f("UPCOMING", day, "TBC", at(23, 59)) is False)
    check("no clock given: the time cannot drop it", f("UPCOMING", day, "09:00", None) is False)
    check("status in progress drops it with no clock", f("IN_PROGRESS", day, "20:00", None) is True)
    check("status final drops it with no clock", f("FINAL", day, None, None) is True)
    check("control: a future game on a later date stays",
          f("UPCOMING", date(2026, 10, 24), "09:00", at(23)) is False)


def player_pure_checks() -> None:
    print("self-service fixtures (pure)")
    svc = load_service()
    sat = "2026-10-17"
    by_date = {sat: [
        {**fx("f-3", team=None, grade="g3", opp="Willetton 3s", home_away="HOME"), "start_time": "13:00", "venue": "Home Oval"},
        {**fx("f-1", team="t-1", grade="g1", opp="Swan Valley 1st XI", home_away="AWAY"), "start_time": "11:00", "venue": "Swan Park"},
        {**fx("f-2", team="t-2", grade="g3", opp="Other 2s", home_away="HOME"), "start_time": "13:00", "venue": "Home Oval"},
    ]}
    names = {"t-3": "3rd XI", "t-1": "1st XI", "t-2": "2nd XI"}
    out = svc.fixtures_for_player(by_date, [("t-3", "g3")], names, {"g3": "Saturday 3s", "g1": "Saturday 1s"})[sat]
    by_id = {f["id"]: f for f in out}
    check("grade-only fixture in my squad's grade is mine", by_id["f-3"]["mine"] is True)
    check("...and is named by my squad, not the grade", by_id["f-3"]["team_name"] == "3rd XI", str(by_id["f-3"]["team_name"]))
    check("another squad's game is not mine", by_id["f-1"]["mine"] is False and by_id["f-1"]["team_name"] == "1st XI")
    check("a fixture naming another squad is not mine even in my grade", by_id["f-2"]["mine"] is False)
    check("time, venue, home or away travel with each game",
          by_id["f-1"]["start_time"] == "11:00" and by_id["f-1"]["venue"] == "Swan Park" and by_id["f-1"]["home_away"] == "AWAY")
    check("no internal team_id or grade_id leaves the service",
          all("team_id" not in f and "grade_id" not in f for f in out))
    none = svc.fixtures_for_player(by_date, [], names, {})[sat]
    check("a player in no squad has nothing marked mine", not any(f["mine"] for f in none))
    check("grade name is the last resort for our side",
          svc.fixtures_for_player({sat: [fx("x", grade="g1")]}, [], {}, {"g1": "Saturday 1s"})[sat][0]["team_name"] == "Saturday 1s")


async def public_route_checks(db_url: str) -> None:
    print("GET /public/availability/{token}/me (real Postgres)")
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config.settings import settings
    from app.models.db import Base, Organisation, Player, Team, TeamMember, Grade, Season, Fixture
    from app.routers import public_availability as pa
    from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        # Lifespan-only tables the grade classification (junior hiding, women's
        # side) reads through grade_alias_map; copied from the lifespan.
        for stmt in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(stmt))

    org_id, season_id = uuid.uuid4(), uuid.uuid4()
    g3, g1 = uuid.uuid4(), uuid.uuid4()
    t3, t1 = uuid.uuid4(), uuid.uuid4()
    p_in, p_out = uuid.uuid4(), uuid.uuid4()
    token = "tok-" + uuid.uuid4().hex
    sat = date.today() + timedelta(days=6)

    def req_for(pid):
        c = jose_jwt.encode({"club": str(org_id), "pid": str(pid), "typ": "avail",
                             "exp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        return Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

    async with Session() as s:
        s.add(Organisation(id=org_id, name=f"Pub {org_id.hex[:6]}", slug=f"pub-{org_id.hex[:8]}",
                           module_overrides=["select"], availability_link_token=token,
                           availability_self_service_enabled=True, availability_show_squad=True))
        await s.flush()
        s.add(Season(id=season_id, organisation_id=org_id, name="2026/27"))
        await s.flush()
        s.add(Grade(id=g3, season_id=season_id, name="Saturday 3s"))
        s.add(Grade(id=g1, season_id=season_id, name="Saturday 1s"))
        await s.flush()
        s.add(Team(id=t3, organisation_id=org_id, name="3rd XI", short_name="3s", grade_id=g3))
        s.add(Team(id=t1, organisation_id=org_id, name="1st XI", short_name="1s", grade_id=g1))
        s.add(Player(id=p_in, organisation_id=org_id, name="Mine, Mick"))
        s.add(Player(id=p_out, organisation_id=org_id, name="Nosquad, Nat"))
        await s.flush()
        s.add(TeamMember(team_id=t3, player_id=p_in, organisation_id=org_id))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=g3, team_id=None, source="manual",
                      played_on=sat, start_time="13:00", venue="Home Oval", home_away="HOME", opponent_name="Willetton 3s"))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=g1, team_id=t1, source="manual",
                      played_on=sat, start_time="11:00", venue="Swan Park", home_away="AWAY", opponent_name="Swan Valley 1st XI"))
        await s.commit()
        mine = await pa.get_me(token, req_for(p_in), db=s)
        nosquad = await pa.get_me(token, req_for(p_out), db=s)

    fx_in = {f["opponent_name"]: f for f in (mine["dates"][0]["fixtures"] if mine.get("dates") else [])}
    f3, f1 = fx_in.get("Willetton 3s", {}), fx_in.get("Swan Valley 1st XI", {})
    check("route: both games listed for the date", len(fx_in) == 2, str(list(fx_in)))
    check("route: my game carries time, venue, home, my squad's name",
          f3.get("start_time") == "13:00" and f3.get("venue") == "Home Oval" and f3.get("home_away") == "HOME" and f3.get("team_name") == "3rd XI", str(f3))
    check("route: my game is marked mine", f3.get("mine") is True)
    check("route: the 1st XI game is shown, away, not mine",
          f1.get("mine") is False and f1.get("home_away") == "AWAY" and f1.get("team_name") == "1st XI" and f1.get("start_time") == "11:00", str(f1))
    check("route: has_squad true for a squad player", mine.get("has_squad") is True)
    check("route: response carries no team_id or grade_id",
          all("team_id" not in f and "grade_id" not in f for d in mine.get("dates", []) for f in d["fixtures"]))
    check("route: a player in no squad has has_squad false and nothing mine",
          nosquad.get("has_squad") is False and not any(f.get("mine") for d in nosquad.get("dates", []) for f in d["fixtures"]), str(nosquad.get("has_squad")))

    async with Session() as s:
        await s.execute(delete(Fixture).where(Fixture.organisation_id == org_id))
        await s.execute(delete(TeamMember).where(TeamMember.organisation_id == org_id))
        await s.execute(delete(Player).where(Player.organisation_id == org_id))
        await s.execute(delete(Team).where(Team.organisation_id == org_id))
        await s.execute(delete(Grade).where(Grade.season_id == season_id))
        await s.execute(delete(Season).where(Season.id == season_id))
        await s.execute(delete(Organisation).where(Organisation.id == org_id))
        await s.commit()
    await engine.dispose()


async def show_squad_checks(db_url: str) -> None:
    print("show squad switch (real Postgres)")
    from datetime import datetime, timezone
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config.settings import settings
    from app.models.db import Base, Organisation, Player, Team, TeamMember, Grade, Season, Fixture
    from app.routers import availability as av
    from app.routers import public_availability as pa
    from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS
    from app.services.availability_squad_ddl import STATEMENTS as SQUAD_DDL

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        # Lifespan-only tables the grade classification (junior hiding, women's
        # side) reads through grade_alias_map; copied from the lifespan.
        for stmt in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(stmt))
        for stmt in SQUAD_DDL:      # the lifespan's own statements: they must re-run cleanly
            await conn.execute(text(stmt))
            await conn.execute(text(stmt))

    org_id, season_id, g3, t3, pid = (uuid.uuid4() for _ in range(5))
    token = "tok-" + uuid.uuid4().hex
    sat = date.today() + timedelta(days=6)
    async with Session() as s:
        # No availability_show_squad given: the column default is what a club gets.
        s.add(Organisation(id=org_id, name=f"Squad {org_id.hex[:6]}", slug=f"sq-{org_id.hex[:8]}",
                           module_overrides=["select"], availability_link_token=token,
                           availability_self_service_enabled=True))
        await s.flush()
        s.add(Season(id=season_id, organisation_id=org_id, name="2026/27")); await s.flush()
        s.add(Grade(id=g3, season_id=season_id, name="Saturday 3s")); await s.flush()
        s.add(Team(id=t3, organisation_id=org_id, name="3rd XI", grade_id=g3))
        s.add(Player(id=pid, organisation_id=org_id, name="Hidden, Hal")); await s.flush()
        s.add(TeamMember(team_id=t3, player_id=pid, organisation_id=org_id))
        s.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=g3, team_id=None, source="manual",
                      played_on=sat, start_time="13:00", venue="Home Oval", home_away="HOME", opponent_name="Willetton 3s"))
        await s.commit()
        club = await s.get(Organisation, org_id)
        c = jose_jwt.encode({"club": str(org_id), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(timezone.utc) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        req = Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})

        async def me():
            return await pa.get_me(token, req, db=s)
        def flat(body):
            return [f for d in body["dates"] for f in d["fixtures"]]

        off = await me()
        check("default is off", club.availability_show_squad is False)
        check("off: no game is marked mine", flat(off) and not any(f.get("mine") for f in flat(off)), str(flat(off)))
        check("off: has_squad is false", off.get("has_squad") is False)
        check("off: the squad's name is not on the page (the grade is)",
              all(f.get("team_name") != "3rd XI" for f in flat(off)) and flat(off)[0].get("team_name") == "Saturday 3s", str(flat(off)[0].get("team_name")))
        check("off: the game itself (time, venue, opponent) still shows",
              flat(off)[0].get("start_time") == "13:00" and flat(off)[0].get("opponent_name") == "Willetton 3s")
        check("admin read says show_squad false", (await av.get_self_service(db=s, club=club, user=None)).get("show_squad") is False)

        on_payload = await av.update_self_service(av.SelfServiceUpdate(show_squad=True), db=s, club=club, user=None)
        check("admin write turns it on", on_payload.get("show_squad") is True)
        on = await me()
        check("on: the player's game is marked mine and named by the squad",
              flat(on)[0].get("mine") is True and flat(on)[0].get("team_name") == "3rd XI" and on.get("has_squad") is True)

        kept = await av.update_self_service(av.SelfServiceUpdate(require_pin=False), db=s, club=club, user=None)
        check("a key that is not sent leaves show_squad alone", kept.get("show_squad") is True and kept.get("require_pin") is False)
        off_payload = await av.update_self_service(av.SelfServiceUpdate(show_squad=False), db=s, club=club, user=None)
        check("admin write turns it off again", off_payload.get("show_squad") is False)
        check("off again: nothing mine", not any(f.get("mine") for f in flat(await me())))

    async with Session() as s:
        await s.execute(delete(Fixture).where(Fixture.organisation_id == org_id))
        await s.execute(delete(TeamMember).where(TeamMember.organisation_id == org_id))
        await s.execute(delete(Player).where(Player.organisation_id == org_id))
        await s.execute(delete(Team).where(Team.organisation_id == org_id))
        await s.execute(delete(Grade).where(Grade.season_id == season_id))
        await s.execute(delete(Season).where(Season.id == season_id))
        await s.execute(delete(Organisation).where(Organisation.id == org_id))
        await s.commit()
    await engine.dispose()


async def started_route_checks(db_url: str) -> None:
    print("started games, shipped routes (real Postgres)")
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from jose import jwt as jose_jwt
    from starlette.requests import Request
    from sqlalchemy import delete, text
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from app.config.settings import settings
    from app.models.db import Base, Organisation, Player, Team, TeamMember, Grade, Season, Fixture
    from app.routers import availability as av
    from app.routers import public_availability as pa
    from app.services.selection_rule_ddl import SELECTION_RULE_STATEMENTS

    engine = create_async_engine(db_url, echo=False)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        for stmt in SELECTION_RULE_STATEMENTS:
            await conn.execute(text(stmt))
        # Lifespan-only tables the grade classification (junior hiding, women's
        # side) reads through grade_alias_map; copied from the lifespan.
        for stmt in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(stmt))

    tz = "Australia/Perth"
    today_local = datetime.now(ZoneInfo(tz)).date()
    next_sat = today_local + timedelta(days=(5 - today_local.weekday()) % 7 + 7)
    org_id, season_id, g3, t3, pid = (uuid.uuid4() for _ in range(5))
    token = "tok-" + uuid.uuid4().hex
    ids = {k: uuid.uuid4() for k in ("started", "later", "nextweek", "inprog", "untimed")}

    def fixture(key, on, start, status="UPCOMING", opp=None):
        return Fixture(id=ids[key], organisation_id=org_id, grade_id=g3, team_id=None, source="manual",
                       played_on=on, start_time=start, status=status, opponent_name=opp or key, home_away="HOME")

    async with Session() as s:
        s.add(Organisation(id=org_id, name=f"Started {org_id.hex[:6]}", slug=f"st-{org_id.hex[:8]}",
                           module_overrides=["select"], availability_link_token=token,
                           availability_self_service_enabled=True))
        await s.flush()
        s.add(Season(id=season_id, organisation_id=org_id, name="2026/27")); await s.flush()
        s.add(Grade(id=g3, season_id=season_id, name="Saturday 3s")); await s.flush()
        s.add(Team(id=t3, organisation_id=org_id, name="3rd XI", grade_id=g3))
        s.add(Player(id=pid, organisation_id=org_id, name="Started, Sam")); await s.flush()
        s.add(TeamMember(team_id=t3, player_id=pid, organisation_id=org_id))
        # today in the viewer's timezone: one that began at 00:00, one that begins at 23:59,
        # one marked in progress, one with no start time, and next Saturday's game.
        s.add(fixture("started", today_local, "00:00"))
        s.add(fixture("later", today_local, "23:59"))
        s.add(fixture("inprog", today_local, "23:58", status="IN_PROGRESS"))
        s.add(fixture("untimed", today_local, None))
        s.add(fixture("nextweek", next_sat, "13:00"))
        await s.commit()
        club = await s.get(Organisation, org_id)
        async def matrix(tz_value):
            try:
                return await av.availability_matrix(tz=tz_value, db=s, club=club)
            except TypeError:   # the previous route has no tz: report, do not crash
                return await av.availability_matrix(db=s, club=club)
        with_tz, without, bad_tz = await matrix(tz), await matrix(None), await matrix("Not/AZone")
        c = jose_jwt.encode({"club": str(org_id), "pid": str(pid), "typ": "avail",
                             "exp": datetime.now(ZoneInfo("UTC")) + timedelta(days=1)},
                            settings.secret_key, algorithm=settings.algorithm)
        req = Request({"type": "http", "headers": [(b"cookie", f"{pa.COOKIE_NAME}={c}".encode())]})
        try:
            me_tz = await pa.get_me(token, req, tz=tz, db=s)
        except TypeError:
            me_tz = await pa.get_me(token, req, db=s)
        me_plain = await pa.get_me(token, req, db=s)

    def opps(body):
        return sorted(f["opponent_name"] for d in body["dates"] for f in d["fixtures"])
    check("matrix with tz: the 00:00 game has gone", "started" not in opps(with_tz), str(opps(with_tz)))
    check("matrix with tz: the game that has not started stays", "later" in opps(with_tz))
    check("matrix with tz: the in-progress game has gone", "inprog" not in opps(with_tz))
    check("matrix with tz: the untimed game stays for its date", "untimed" in opps(with_tz))
    check("matrix with tz: next week's game stays", "nextweek" in opps(with_tz))
    check("control: with no tz only the status drops a game (date-only, as before)",
          "started" in opps(without) and "inprog" not in opps(without), str(opps(without)))
    check("a bad timezone is ignored, not an error", "started" in opps(bad_tz))
    check("self-service page with tz: the 00:00 game has gone, the rest stay",
          "started" not in opps(me_tz) and {"later", "untimed", "nextweek"} <= set(opps(me_tz)), str(opps(me_tz)))
    check("self-service page without tz still lists the 00:00 game", "started" in opps(me_plain))
    sn = with_tz.get("squad_next", {}).get(str(t3), {})
    check("the squad's next game skips what has started (today, 23:59 or next week)",
          sn.get("date") in (today_local.isoformat(), next_sat.isoformat()) and sn.get("fixture_id") != str(ids["started"]), str(sn))

    async with Session() as s:
        await s.execute(delete(Fixture).where(Fixture.organisation_id == org_id))
        await s.execute(delete(TeamMember).where(TeamMember.organisation_id == org_id))
        await s.execute(delete(Player).where(Player.organisation_id == org_id))
        await s.execute(delete(Team).where(Team.organisation_id == org_id))
        await s.execute(delete(Grade).where(Grade.season_id == season_id))
        await s.execute(delete(Season).where(Season.id == season_id))
        await s.execute(delete(Organisation).where(Organisation.id == org_id))
        await s.commit()
    await engine.dispose()


def main() -> int:
    pure_checks()
    started_pure_checks()
    player_pure_checks()
    db_url = os.environ.get("DATABASE_URL")
    if db_url:
        asyncio.run(route_checks(db_url))
        asyncio.run(public_route_checks(db_url))
        asyncio.run(started_route_checks(db_url))
        asyncio.run(show_squad_checks(db_url))
    else:
        print("matrix route: SKIPPED (no DATABASE_URL), only the pure rule was run")
    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print("  failed:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
