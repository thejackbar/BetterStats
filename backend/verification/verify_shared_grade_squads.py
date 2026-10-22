"""Verification: two of the club's teams in ONE grade each keep their own squad, against a real Postgres.

Reported (Applecross): the 8th XI and the 10th XI both play One Day Grade 6 Black.
Sync puts a fixture on a squad by grade, so both teams' games landed on one squad and
had to be moved by hand, every round. Cricket Australia names our own team on every
fixture ("Applecross 10th XI"); that name now tells the two apart.

Drives the SHIPPED `sync_fixtures` route body (CA stubbed at the network layer) and
`squad_sides.assign_fixtures`, never a re-implementation:

  * the 10th XI's game goes to the 10th XI squad, the 8th XI's to the 8th XI squad
  * a second sync leaves both where they are (nobody re-links anything)
  * saving a squad (assign_fixtures) does not pull the other team's game across
  * a team name with no XI number, or a number no squad carries, is left to the grade
  * a game somebody picked by hand stays where it was put

CONTROL MODE: against the previous commit the 10th XI's games land on the 8th XI
squad and the "left to the grade" checks still pass.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_shared_grade_squads.py
"""
from __future__ import annotations

import asyncio
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
from app.models.db import Fixture, Grade, Organisation, Season, Team

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def _scalar(sql, **kw):
    async with Session() as db:
        return (await db.execute(text(sql), kw)).scalar()


async def main():
    await base.build_schema()
    import app.routers.fixtures as fixtures_r
    from app.services import squad_sides

    org, season, grade = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    T8, T10, T12 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    d1 = date.today() + timedelta(days=7)
    async with Session() as db:
        db.add(Organisation(id=org, name="Applecross CC", slug=f"acc-{org.hex[:8]}"))
        db.add(Season(id=season, organisation_id=org, name="Summer 2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade, season_id=season, name="One Day Grade 6 Black", categories=["senior"]))
        await db.flush()
        db.add(Team(id=T8, organisation_id=org, name="Applecross 8th XI", sequence=8, grade_id=grade))
        db.add(Team(id=T10, organisation_id=org, name="Applecross 10th XI", sequence=10))
        db.add(Team(id=T12, organisation_id=org, name="Applecross 12th XI", sequence=12, is_active=False))
        await db.flush()
        # The 8th XI squad plays the grade on purpose (a stored team); the 10th XI has no claim on it.
        await db.execute(text(
            "INSERT INTO team_sides (team_id, organisation_id, grade_key, grade_name, position) "
            "VALUES (:t, :o, 'one day grade 6 black', 'One Day Grade 6 Black', 0)"), {"t": T8, "o": org})
        await db.commit()

    # key -> (our team's name, home/away)
    spec = {
        "f10": "Applecross 10th XI",
        "f8": "Applecross 8th XI",
        "fname": "Applecross OD6 Black",     # no XI number: the grade decides
        "f12": "Applecross 12th XI",         # a number only an inactive squad carries: the grade decides
        "f10-hand": "Applecross 10th XI",    # picked by hand onto the 8th XI squad
    }
    ids = {}
    async with Session() as db:
        for k in spec:
            f = Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=grade, source="grassroots",
                        playhq_id=f"sync-{k}", played_on=d1, start_time="12:00", status="UPCOMING", round=k)
            if k == "f10-hand":
                f.team_id = T8
                if hasattr(Fixture, "team_pinned"):
                    f.team_pinned = True
            db.add(f)
            ids[k] = f.id
        await db.commit()
    games = [{"id": f"sync-{k}", "played_at": d1.isoformat(), "time": "12:00", "home_team": name,
              "away_team": "Opposition", "db_grade_id": str(grade), "grade_name": "One Day Grade 6 Black",
              "round": k, "venue": "V", "status": "UPCOMING"} for k, name in spec.items()]

    async def fake_games(db, club, force=False):
        return games, {}
    fixtures_r.org_grassroots_fixtures_checked = fake_games

    async def team_of(key):
        return await _scalar("SELECT team_id FROM fixtures WHERE id=:f", f=ids[key])

    async def sync():
        async with Session() as db:
            await fixtures_r.sync_fixtures(db=db, club=await db.get(Organisation, org), _user=None)

    print("# A. Sync tells the two teams apart by our team's name")
    await sync()
    check("the 10th XI's game goes to the 10th XI squad", await team_of("f10"), T10)
    check("the 8th XI's game goes to the 8th XI squad", await team_of("f8"), T8)
    check("a name with no XI number is left to the grade (8th XI squad plays it)", await team_of("fname"), T8)
    check("a number only an inactive squad carries is left to the grade", await team_of("f12"), T8)
    check("a game picked by hand stays where it was put", await team_of("f10-hand"), T8)

    print("\n# B. Nobody has to re-link it")
    await sync()
    check("a second sync leaves the 10th XI's game on its squad", await team_of("f10"), T10)
    check("...and the 8th XI's on its own", await team_of("f8"), T8)

    print("\n# C. Saving a squad does not pull the other team's game across")
    async with Session() as db:
        await squad_sides.assign_fixtures(db, org, T8)
        await db.commit()
    check("assigning the 8th XI squad's fixtures leaves the 10th XI's game alone", await team_of("f10"), T10)
    check("...and still keeps the 8th XI's", await team_of("f8"), T8)

    print("\n# D. The name rule itself")
    async with Session() as db:
        sides = await squad_sides.load(db, org)
    pick = getattr(sides, "squad_for_team_name", None)
    got = lambda name: getattr(pick(grade, name), "id", None) if pick else None   # noqa: E731
    check("10th XI name -> the 10th XI squad", got("Applecross 10th XI"), str(T10))
    check("8th XI name -> None (the grade's own squad already carries 8)", got("Applecross 8th XI"), None)
    check("no XI number -> None", got("Applecross OD6 Black"), None)
    check("a number nobody carries -> None", got("Applecross 9th XI"), None)
    check("an inactive squad's number -> None", got("Applecross 12th XI"), None)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
