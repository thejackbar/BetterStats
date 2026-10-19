"""Verification: "fill from last week" follows the GRADE, against a real Postgres.

Gisborne: the 3rd and 4th XI grades (07J, 09J) were linked to the wrong squads, then
fixed. Past games are not re-assigned when a squad's teams are re-linked, so last
week's two games both still sat on one squad and "fill from last week" returned
whichever of them was latest: a mixed bag of the other side's players.

Drives the SHIPPED route body `previous_xi`, never a re-implementation:

  * last week's XI is the same grade's, even when that game sits on another squad
  * two grades' games on one squad are not mixed (the later game is the wrong grade)
  * a grade with no saved XI of its own falls back to the squad's last side, as before
  * a fixture with no squad reads its grade; a grade nobody has played reads nothing
  * the club's picked team (`side_key`) on a fixture with no grade is read by that team
  * another club's game in the same grade name is never read

CONTROL MODE: run against the previous `routers/selection.py`; every key is read with
`.get`, so the control FAILS the grade checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_previous_xi_grade.py
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
    G = {n: uuid.uuid4() for n in ("07J", "09J", "10C", "Cup")}
    OG = uuid.uuid4()
    T = {n: uuid.uuid4() for n in ("Thirds", "Fourths")}
    P = {n: uuid.uuid4() for n in ("a1", "a2", "b1", "b2", "c1", "x1")}
    last = date.today() - timedelta(days=7)
    nxt = date.today() + timedelta(days=7)
    FX: dict = {}

    async with Session() as db:
        db.add(Organisation(id=org, name="Gisborne CC", slug=f"gis-{org.hex[:8]}"))
        db.add(Organisation(id=other_org, name="Other CC", slug=f"oth-{other_org.hex[:8]}"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        db.add(Season(id=other_season, organisation_id=other_org, name="Summer", year=2026))
        await db.flush()
        for n, gid in G.items():
            db.add(Grade(id=gid, season_id=season, name=n, categories=["senior"]))
        db.add(Grade(id=OG, season_id=other_season, name="07J", categories=["senior"]))
        await db.flush()
        # The squads after the club fixed them: 07J is the 3rds', 09J the 4ths'.
        db.add(Team(id=T["Thirds"], organisation_id=org, name="3rd XI", sequence=3, grade_id=G["07J"]))
        db.add(Team(id=T["Fourths"], organisation_id=org, name="4th XI", sequence=4, grade_id=G["09J"]))
        for n, pid in P.items():
            db.add(Player(id=pid, organisation_id=other_org if n == "x1" else org, name=n, is_player=True))
        await db.flush()

        def fx(key, grade, on, team=None, start="13:00", organisation=org, side_key=None):
            f = Fixture(id=uuid.uuid4(), organisation_id=organisation, grade_id=grade, team_id=team,
                        source="grassroots", played_on=on, start_time=start, status="UPCOMING",
                        opponent_name=key, label=key, round=key)
            if side_key is not None and hasattr(f, "side_key"):
                f.side_key = side_key
            db.add(f)
            FX[key] = f.id
            return f

        # Last week both games sat on the 3rds' squad (the old, crossed link); the 09J game is later.
        fx("past-07J", G["07J"], last, team=T["Thirds"], start="10:00")
        fx("past-09J", G["09J"], last, team=T["Thirds"], start="13:00")
        fx("past-10C", G["10C"], last, team=T["Fourths"])
        fx("past-other", OG, last - timedelta(days=1), organisation=other_org)
        fx("up-07J", G["07J"], nxt, team=T["Thirds"], start="10:00")
        fx("up-09J", G["09J"], nxt, team=T["Fourths"], start="13:00")
        fx("up-cup", G["Cup"], nxt, team=T["Thirds"])
        fx("up-nosquad", G["09J"], nxt + timedelta(days=1))
        fx("up-picked", None, nxt, team=T["Fourths"], side_key="10c")
        await db.flush()
        lineups = {"past-07J": ["a1", "a2"], "past-09J": ["b1", "b2"], "past-10C": ["c1"], "past-other": ["x1"]}
        for key, names in lineups.items():
            for i, n in enumerate(names):
                db.add(FixtureLineup(fixture_id=FX[key], player_id=P[n], organisation_id=other_org if key == "past-other" else org,
                                     batting_order=i + 1))
        await db.commit()

    async def prev(key):
        async with Session() as db:
            club = await db.get(Organisation, org)
            return await sel.previous_xi(str(FX[key]), db=db, club=club)

    def ids(r, *names):
        return sorted(str(P[n]) for n in names)

    print("\n# A. The grade says which side played")
    r = await prev("up-07J")
    check("07J's last week is the 07J game's XI, not the later 09J game on the same squad",
          sorted((r or {}).get("player_ids") or []), ids(r, "a1", "a2"))
    check("...and it names that game as the source", (r or {}).get("source_fixture_id"), str(FX["past-07J"]))
    r = await prev("up-09J")
    check("09J's last week is the 09J game's XI even though it was filed on the 3rds' squad",
          sorted((r or {}).get("player_ids") or []), ids(r, "b1", "b2"))
    check("the XI keeps its batting order", (r or {}).get("player_ids"), [str(P["b1"]), str(P["b2"])])

    print("\n# B. Fallbacks and edges")
    r = await prev("up-cup")
    check("a grade nobody has a saved XI for falls back to the squad's last side (as before)",
          (r or {}).get("source_fixture_id"), str(FX["past-09J"]))
    r = await prev("up-nosquad")
    check("a fixture with no squad reads its grade", sorted((r or {}).get("player_ids") or []), ids(r, "b1", "b2"))
    if hasattr(Fixture, "side_key"):
        r = await prev("up-picked")
        check("a picked team the squad does not have falls back to the squad, not to guesswork",
              (r or {}).get("source_fixture_id"), str(FX["past-10C"]))

    print("\n# C. Never another club's game")
    async with Session() as db:
        await db.execute(text("DELETE FROM fixture_lineups WHERE fixture_id=:f"), {"f": FX["past-07J"]})
        await db.commit()
    r = await prev("up-07J")
    check("with 07J's own XI gone it does not read the other club's 07J game",
          str(P["x1"]) in ((r or {}).get("player_ids") or []), False)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
