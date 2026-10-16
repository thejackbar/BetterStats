"""Verification: a fixture's "our team" is one of a squad's teams, against a real Postgres.

Asked for (Gisborne): "In fixtures, 'our team' isn't a squad that it needs to be synced
to, it's a side that needs to be selected which has a squad assigned. Currently I can
only change our team to a squad."

Drives the SHIPPED route bodies (`create_fixture`, `update_fixture`, `list_fixtures`,
`selection_overview`) and `assemble_selection`:

  * a hand-made fixture takes a squad AND one of its teams ("MACs, 2nd XI")
  * a synced fixture keeps the grade Cricket Australia gave it, and the club's own
    choice of team sits beside it (`fixtures.side_key`): it is called and ranked by
    the picked team, in the fixtures list, the selection overview and the pool
  * a team that is not one of the squad's is refused, not guessed
  * moving the fixture to another squad drops the old team; clearing the squad too
  * a squad with one team needs no team picked and reads as before
  * the sync never writes the pick

CONTROL MODE: against the previous commit `side_key` is unknown; every key is read with
`.get`, so the control FAILS the checks that need the feature instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_fixture_side.py
"""
from __future__ import annotations

import asyncio
import importlib
import inspect
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
from app.models.db import Fixture, Grade, Organisation, Season, Team, User

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
        for mod in ("team_sides_ddl", "fixture_side_ddl", "fixture_pin_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
    import app.routers.teams as teams_r
    import app.routers.fixtures as fixtures_r
    import app.routers.selection as sel
    from app.services.grade_labels import grade_key
    from app.services.selection_pool import assemble_selection

    org, user_id, season = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    names = ["1st Grade", "2nd Grade", "3rd Grade", "Womens A", "Womens B"]
    G = {n: uuid.uuid4() for n in names}
    K = {n: grade_key(n) for n in names}
    T = {n: uuid.uuid4() for n in ("MACs", "Thirds", "Women")}
    async with Session() as db:
        db.add(Organisation(id=org, name="Gisborne CC", slug=f"gis-{org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season, organisation_id=org, name="Summer 2026/27", year=2026))
        await db.flush()
        for n in names:
            db.add(Grade(id=G[n], season_id=season, name=n, categories=["womens"] if n.startswith("Women") else ["senior"]))
        await db.flush()
        for n, seq in (("MACs", 1), ("Thirds", 3), ("Women", 50)):
            db.add(Team(id=T[n], organisation_id=org, name=n, sequence=seq))
        await db.commit()

    d1 = date.today() + timedelta(days=7)
    FX = {}
    async with Session() as db:
        for key, grade, source in (("synced-1st", "1st Grade", "grassroots"), ("synced-3rd", "3rd Grade", "grassroots")):
            f = Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=G[grade], source=source, played_on=d1,
                        start_time="13:00", status="UPCOMING", opponent_name=key, label=key, round=key)
            db.add(f)
            FX[key] = f.id
        await db.commit()

    async def as_admin(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            who = "user" if "user" in inspect.signature(fn).parameters else "_user"
            try:
                return await fn(*a, db=db, club=club, **{who: user}, **kw), None
            except HTTPException as e:
                return None, e

    async def as_club(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await fn(*a, db=db, club=club, **kw), None
            except HTTPException as e:
                return None, e

    def body(cls, **kw):
        # Control: an old model ignores a key it does not know, so the check below fails, not the run.
        return cls(**kw)

    if hasattr(teams_r, "SideIn"):
        SideIn = teams_r.SideIn
        await as_admin(teams_r.update_team, str(T["MACs"]), teams_r.TeamUpdate(sides=[SideIn(grade_id=str(G["1st Grade"])), SideIn(grade_id=str(G["2nd Grade"]))]))
        await as_admin(teams_r.update_team, str(T["Women"]), teams_r.TeamUpdate(sides=[SideIn(grade_id=str(G["Womens A"])), SideIn(grade_id=str(G["Womens B"]))]))
    await as_admin(teams_r.update_team, str(T["Thirds"]), teams_r.TeamUpdate(grade_id=str(G["3rd Grade"])))

    def row(lst, rnd):
        return next((f for f in (lst or []) if f.get("round") == rnd), {})

    print("\n# A. A hand-made fixture takes a squad and one of its teams")
    r, e = await as_admin(fixtures_r.create_fixture, body(
        fixtures_r.FixtureCreate, opponent_name="Wallan", round="hand", home_away="AWAY", played_on=d1,
        team_id=str(T["MACs"]), side_key=K["2nd Grade"]))
    check("it saves", e is None, True)
    check("...as the 2nd XI of MACs", ((r or {}).get("team_name"), (r or {}).get("squad_name")), ("2nd XI", "MACs"))
    check("...ranked 2, and it says which team it is", ((r or {}).get("team_sequence"), (r or {}).get("side_key")), (2, K["2nd Grade"]))

    print("\n# B. A synced fixture keeps its grade; the club's pick sits beside it")
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, team_id=str(T["MACs"])))
    check("a squad with no team picked reads by the fixture's grade (1st XI)", (r or {}).get("team_name"), "1st XI")
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, team_id=str(T["MACs"]), side_key=K["2nd Grade"]))
    check("picking the 2nd XI for it makes it the 2nd XI", (r or {}).get("team_name"), "2nd XI")
    check("...ranked 2", (r or {}).get("team_sequence"), 2)
    check("...its grade is still the one Cricket Australia gave it", (await _scalar("SELECT grade_id FROM fixtures WHERE id=:f", f=FX["synced-1st"])) == G["1st Grade"], True)
    fl, _ = await as_club(fixtures_r.list_fixtures)
    check("the fixtures list says the same", row(fl, "synced-1st").get("team_name"), "2nd XI")
    ov, _ = await as_club(sel.selection_overview)
    ovr = next((f for f in (ov or {}).get("fixtures", []) if f.get("id") == str(FX["synced-1st"])), {})
    check("the selection overview calls it the 2nd XI, rank 2", (ovr.get("team_name"), ovr.get("team_sequence")), ("2nd XI", 2))
    async with Session() as db:
        fx = await db.get(Fixture, FX["synced-1st"])
        pool = await assemble_selection(db, await db.get(Organisation, org), fx)
    check("the selection pool names it the 2nd XI too", ((pool or {}).get("fixture") or {}).get("team_name"), "2nd XI")
    check("the sync never sets a pick (it only drops one when it moves a fixture)", inspect.getsource(fixtures_r.sync_fixtures).count("side_key"), 1)

    print("\n# C. A team that is not the squad's is refused")
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, side_key=K["Womens A"]))
    check("MACs has no Womens A team: refused", getattr(e, "status_code", None), 400)
    check("...and nothing changed", (await _scalar("SELECT side_key FROM fixtures WHERE id=:f", f=FX["synced-1st"])), K["2nd Grade"])
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-3rd"]), body(fixtures_r.FixtureUpdate, side_key=K["2nd Grade"]))
    check("a team with no squad on the fixture is refused", getattr(e, "status_code", None), 400)

    print("\n# D. Moving the fixture drops the old team")
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, team_id=str(T["Women"])))
    check("another squad, no team named: the 2nd XI pick is gone", (await _scalar("SELECT side_key FROM fixtures WHERE id=:f", f=FX["synced-1st"])), None)
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, team_id=str(T["Women"]), side_key=K["Womens B"]))
    check("naming the squad and its team together works", ((r or {}).get("squad_name"), (r or {}).get("side_key")), ("Women", K["Womens B"]))
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-1st"]), body(fixtures_r.FixtureUpdate, team_id=None))
    check("no team assigned clears it", ((r or {}).get("team_id"), (await _scalar("SELECT side_key FROM fixtures WHERE id=:f", f=FX["synced-1st"]))), (None, None))

    print("\n# E. A single-team squad needs no pick")
    r, e = await as_admin(fixtures_r.update_fixture, str(FX["synced-3rd"]), body(fixtures_r.FixtureUpdate, team_id=str(T["Thirds"])))
    check("it reads as before", ((r or {}).get("team_name"), (r or {}).get("team_sequence")), ("Thirds", 3))

    print("\n# F. Sync puts a synced fixture on the squad that plays its grade")
    # Earlier name matching left women's games on the men's squad and a 3rd Grade game on MACs.
    ids = {}
    async with Session() as db:
        for key, grade, tid, pinned in (
            ("w-wrong", "Womens A", T["MACs"], False),     # guessed wrong by name: should move
            ("w-pinned", "Womens A", T["MACs"], True),     # somebody picked it: stays
            ("w-none", "Womens B", None, False),           # nothing yet: the squad claims it
            ("t-wrong", "3rd Grade", T["MACs"], False),    # the 3rds are linked the old way (one grade)
            ("m-right", "1st Grade", T["MACs"], False),    # already right: untouched
        ):
            f = Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=G[grade], team_id=tid, source="grassroots",
                        playhq_id=f"sync-{key}", played_on=d1, start_time="13:00", status="UPCOMING", opponent_name=key, round=key)
            if hasattr(Fixture, "team_pinned"):
                f.team_pinned = pinned
            db.add(f)
            ids[key] = f.id
        await db.commit()
    games = [{"id": f"sync-{k}", "played_at": d1.isoformat(), "time": "13:00", "home_team": "Gisborne", "away_team": "Opp",
              "db_grade_id": str(G[g]), "grade_name": g, "round": k, "venue": "V", "status": "UPCOMING"}
             for k, g in (("w-wrong", "Womens A"), ("w-pinned", "Womens A"), ("w-none", "Womens B"), ("t-wrong", "3rd Grade"), ("m-right", "1st Grade"))]

    async def fake_games(db, club, force=False):
        return games, {}
    fixtures_r.org_grassroots_fixtures_checked = fake_games
    async with Session() as db:
        club = await db.get(Organisation, org)
        await fixtures_r.sync_fixtures(db=db, club=club, _user=None)

    async def team_of(key):
        return await _scalar("SELECT team_id FROM fixtures WHERE id=:f", f=ids[key])
    check("a women's game on the men's squad moves to the women's squad", await team_of("w-wrong"), T["Women"])
    check("a game nobody has assigned goes to the squad that plays the grade", await team_of("w-none"), T["Women"])
    check("a game on a squad linked the old way moves to its squad", await team_of("t-wrong"), T["Thirds"])
    check("a game already on the right squad stays", await team_of("m-right"), T["MACs"])
    check("a game picked by hand stays where it was put", await team_of("w-pinned"), T["MACs"])

    print("\n# G. Picking a squad by hand pins it against the next sync")
    await as_admin(fixtures_r.update_fixture, str(ids["w-wrong"]), body(fixtures_r.FixtureUpdate, team_id=str(T["MACs"])))
    async with Session() as db:
        await fixtures_r.sync_fixtures(db=db, club=await db.get(Organisation, org), _user=None)
    check("a squad chosen in Edit fixture survives the next sync", await team_of("w-wrong"), T["MACs"])
    await as_admin(fixtures_r.update_fixture, str(ids["w-wrong"]), body(fixtures_r.FixtureUpdate, team_id=None))
    async with Session() as db:
        await fixtures_r.sync_fixtures(db=db, club=await db.get(Organisation, org), _user=None)
    check("choosing No team hands it back to sync", await team_of("w-wrong"), T["Women"])

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


async def _scalar(sql, **kw):
    async with Session() as db:
        return (await db.execute(text(sql), kw)).scalar()


asyncio.run(main())
