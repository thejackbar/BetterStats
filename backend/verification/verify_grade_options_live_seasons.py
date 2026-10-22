"""Verification: the squad team picker lists a newly synced grade, against a real Postgres.

Reported (Applecross): a new team, OD6 Black 2, had its squad created and its fixtures
synced, but "+ Add a team to this squad" did not offer it. `GET /teams/grade-options`
cut the list to the latest two seasons that have grades, so a grade whose season sorted
behind two others (a season CA sent with no start date, or an older one) never reached
the picker.

Drives the SHIPPED `grade_options` route body, never a re-implementation:

  * the latest two seasons with grades are listed, as before
  * a season with no year that holds a grade an upcoming fixture is in is listed
  * an older season that holds such a grade is listed
  * an older season whose only fixtures are in the past is still left out
  * an older season with no fixtures at all is still left out

CONTROL MODE: against the previous commit the two "live" checks FAIL and the two
"left out" checks still pass, so the suite can tell the fix from the old cut-off.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_grade_options_live_seasons.py
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

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Fixture, Grade, Organisation, Season
from app.routers.teams import grade_options

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


async def main() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    org = uuid.uuid4()
    today = date.today()
    # name, year, grade, fixture date (None = no fixture), fixture status
    plan = [
        ("Summer 2026/27", today.year, "1st Grade", None, None),
        ("Summer 2025/26", today.year - 1, "2nd Grade", None, None),
        ("One Day 2026/27", None, "OD6 Black 2", today + timedelta(days=7), "UPCOMING"),
        ("Summer 2023/24", today.year - 3, "Twenty20 Div 9", today + timedelta(days=7), "UPCOMING"),
        ("Summer 2022/23", today.year - 4, "Played Out Grade", today - timedelta(days=30), "FINAL"),
        ("Summer 2021/22", today.year - 5, "Empty Grade", None, None),
    ]
    async with Session() as db:
        db.add(Organisation(id=org, name="Applecross CC", slug=f"app-{org.hex[:8]}"))
        await db.flush()
        for sname, year, gname, fx_date, fx_status in plan:
            sid, gid = uuid.uuid4(), uuid.uuid4()
            db.add(Season(id=sid, organisation_id=org, name=sname, year=year))
            await db.flush()
            db.add(Grade(id=gid, season_id=sid, name=gname))
            await db.flush()
            if fx_date:
                db.add(Fixture(id=uuid.uuid4(), organisation_id=org, grade_id=gid, source="playhq",
                               played_on=fx_date, status=fx_status))
        await db.commit()

    async with Session() as db:
        club = await db.get(Organisation, org)
        out = await grade_options(db=db, club=club)
    names = {g["name"] for s in out["seasons"] for g in s["grades"]}

    print("grade picker")
    check("latest season is listed", "1st Grade" in names)
    check("previous season is listed", "2nd Grade" in names)
    check("no-year season with an upcoming fixture is listed (OD6 Black 2)", "OD6 Black 2" in names)
    check("older season with an upcoming fixture is listed", "Twenty20 Div 9" in names)
    check("older season with only past fixtures is left out", "Played Out Grade" not in names)
    check("older season with no fixtures is left out", "Empty Grade" not in names)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
