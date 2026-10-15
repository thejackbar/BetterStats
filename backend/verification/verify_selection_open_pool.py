"""Verification: the board's default pool order puts everyone who says they are
available and is named nowhere that day first, highest squad first, against a
real Postgres.

Reported: opening the 6th XI Gold selection showed the own squad first and
buried available players from higher grades. Wanted order:
  1. players marked AVAILABLE, in no XI or draft that day, highest squad first
  2. the fixture's own squad
  3. everyone else as before

Drives the SHIPPED `assemble_selection`. CONTROL MODE: run against the commit
BEFORE this change; new keys are read through `.get`, so the control reports the
old order as failed checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_open_pool.py
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
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import (
    Organisation, User, Player, Team, Grade, Season, Fixture, FixtureLineup,
)

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
    from app.services.selection_pool import assemble_selection

    org_id, user_id, season_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    names = {1: "1st XI", 2: "2nd XI", 3: "3rd XI", 4: "4th XI", 5: "5th XI"}
    G = {n: uuid.uuid4() for n in names.values()}
    T = {n: uuid.uuid4() for n in names.values()}

    async with Session() as db:
        db.add(Organisation(id=org_id, name="Verify CC", slug=f"verify-{org_id.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com", password_hash="x"))
        db.add(Season(id=season_id, organisation_id=org_id, name="Summer 2026/27", year=2026))
        await db.flush()
        for n in names.values():
            db.add(Grade(id=G[n], season_id=season_id, name=n, match_formats=["one_day"], categories=["senior"]))
        await db.flush()
        for seq, n in names.items():
            db.add(Team(id=T[n], organisation_id=org_id, name=n, sequence=seq, grade_id=G[n]))
        await db.commit()

    d = date.today() + timedelta(days=21)
    last = date.today() - timedelta(days=14)

    async def fixture(team, on=d):
        fid = uuid.uuid4()
        async with Session() as db:
            db.add(Fixture(id=fid, organisation_id=org_id, grade_id=G[team], team_id=T[team],
                           source="manual", played_on=on, start_time="13:00",
                           status="UPCOMING", label=team))
            await db.commit()
        return fid

    async def player(name, squads, *, status="active"):
        pid = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=pid, organisation_id=org_id, name=name, gender="male", is_player=True,
                          status=status, squad_team_id=T[squads[0]] if squads else None))
            await db.flush()
            for s in squads:
                await db.execute(text(
                    "INSERT INTO team_members (organisation_id, team_id, player_id) VALUES (:o, :t, :p)"),
                    {"o": org_id, "t": T[s], "p": pid})
            await db.commit()
        return pid

    async def avail(pid, status):
        async with Session() as db:
            await db.execute(text(
                "INSERT INTO player_availability (organisation_id, player_id, avail_date, status) "
                "VALUES (:o, :p, :d, :s)"), {"o": org_id, "p": pid, "d": d, "s": status})
            await db.commit()

    async def name_in_xi(fid, pid):
        async with Session() as db:
            db.add(FixtureLineup(fixture_id=fid, player_id=pid, organisation_id=org_id,
                                 batting_order=1, selected_by=user_id))
            await db.commit()

    async def pool(fid):
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            fx = await db.get(Fixture, fid)
            sel = await assemble_selection(db, club, fx)
        return sel["pool"]

    fx4 = await fixture("4th XI")
    fx2 = await fixture("2nd XI")
    two = await player("Two Avail", ["2nd XI"])
    three = await player("Three Avail", ["3rd XI"])
    three_both = await player("Three And Four Avail", ["3rd XI", "4th XI"])
    five = await player("Five Avail", ["5th XI"])
    four_avail = await player("Four Avail", ["4th XI"])
    four_noresp = await player("Four NoResponse", ["4th XI"])
    three_noresp = await player("Three NoResponse", ["3rd XI"])
    three_maybe = await player("Three Maybe", ["3rd XI"])
    three_out = await player("Three Out", ["3rd XI"])
    two_picked = await player("Two Avail Picked", ["2nd XI"])
    two_draft = await player("Two Avail In Draft", ["2nd XI"])
    two_inactive = await player("Two Inactive", ["2nd XI"], status="inactive")
    nosquad = await player("No Squad Avail", [])
    for p_ in (two, three, three_both, five, four_avail, two_picked, two_draft, two_inactive, nosquad):
        await avail(p_, "AVAILABLE")
    await avail(three_maybe, "MAYBE")
    await avail(three_out, "UNAVAILABLE")
    await name_in_xi(fx2, two_picked)
    async with Session() as db:
        await db.execute(text(
            "INSERT INTO selection_drafts (fixture_id, organisation_id, draft) "
            "VALUES (:f, :o, CAST(:d AS jsonb))"), {"f": fx2, "o": org_id, "d": json.dumps({"slots": [str(two_draft)]})})
        await db.commit()

    rows = await pool(fx4)
    order = [r["display_name"] for r in rows]
    by = {r["display_name"]: r for r in rows}
    ix = lambda n: order.index(n) if n in order else 10_000

    print("\n# A. Open picks first, highest squad first")
    check("2nd XI available sorts first", order[0], "Two Avail")
    check("2nd XI before 3rd XI", ix("Two Avail") < ix("Three Avail"), True)
    check("3rd XI before the own squad (4th)", ix("Three Avail") < ix("Four Avail"), True)
    check("3rd+4th squad player ranks by his HIGHER squad", ix("Three And Four Avail") < ix("Four Avail"), True)
    check("own squad available before 5th XI available", ix("Four Avail") < ix("Five Avail"), True)
    check("open picks are exactly the available, unpicked, squadded players",
          sorted(n for n, r in by.items() if r.get("open_seq") is not None),
          sorted(["Two Avail", "Three Avail", "Three And Four Avail", "Five Avail", "Four Avail"]))
    check("open_seq is the highest squad's sequence", (by["Two Avail"].get("open_seq"), by["Three And Four Avail"].get("open_seq"), by["Five Avail"].get("open_seq")), (2, 3, 5))

    print("\n# B. Not open picks: own squad next, then the rest as before")
    for n in ("Four NoResponse",):
        check(f"{n}: own squad follows every open pick", ix(n) > ix("Five Avail"), True)
    check("own squad (no answer) before 3rd XI (no answer)", ix("Four NoResponse") < ix("Three NoResponse"), True)
    check("own squad (no answer) before 3rd XI MAYBE", ix("Four NoResponse") < ix("Three Maybe"), True)
    check("unavailable is not open", by["Three Out"].get("open_seq"), None)
    check("maybe is not open", by["Three Maybe"].get("open_seq"), None)
    check("no answer is not open", by["Four NoResponse"].get("open_seq"), None)

    print("\n# C. Named elsewhere that day is not open")
    check("confirmed in the 2nd XI: not open", by["Two Avail Picked"].get("open_seq"), None)
    check("in the 2nd XI's draft: not open", by["Two Avail In Draft"].get("open_seq"), None)
    check("in the 2nd XI's draft: still pickable (not a clash)", bool(by["Two Avail In Draft"].get("clash")), False)
    check("inactive: not open", (by.get("Two Inactive") or {}).get("open_seq"), None)
    check("no squad: not open", by["No Squad Avail"].get("open_seq"), None)
    check("picked player sorts behind the open picks", ix("Two Avail Picked") > ix("Five Avail"), True)

    print("\n# D. Other fixtures and dates")
    r2 = {r["display_name"]: r for r in await pool(fx2)}
    check("the 2nds' own pool: Two Avail is open (seq 2)", r2["Two Avail"].get("open_seq"), 2)
    nodate = await fixture("4th XI", on=None)
    rn = {r["display_name"]: r for r in await pool(nodate)}
    check("no fixture date: nobody is open (cannot say 'that day')", [n for n, r in rn.items() if r.get("open_seq") is not None], [])
    fx_early = await fixture("4th XI", on=d + timedelta(days=3))
    re_ = {r["display_name"]: r for r in await pool(fx_early)}
    check("another date: the answers were for the first date, so no one is open", [n for n, r in re_.items() if r.get("open_seq") is not None], [])

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        print("\n".join(base.FAILURES))
        sys.exit(1)


asyncio.run(main())
