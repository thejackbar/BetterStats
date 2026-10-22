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

    print("\n# B2. Within a bucket, an answer beats form: Maybe above no answer, above unavailable")
    from app.services.selection_pool import pool_sort_key
    def row(name, availability, score):
        return {"open_seq": None, "tier": 1, "drop_in_from": None, "squad_match": True,
                "availability": availability, "score": score, "display_name": name}
    mixed = [row("Silent Star", "NO_RESPONSE", 90.0), row("Out Star", "UNAVAILABLE", 95.0),
             row("Maybe Low", "MAYBE", 1.0), row("Avail Low", "AVAILABLE", 0.0),
             row("Maybe High", "MAYBE", 20.0)]
    check("same bucket: available, maybes (form order), no answer, unavailable",
          [r["display_name"] for r in sorted(mixed, key=pool_sort_key)],
          ["Avail Low", "Maybe High", "Maybe Low", "Silent Star", "Out Star"])
    check("same answer: form still decides",
          [r["display_name"] for r in sorted([row("B", "NO_RESPONSE", 5.0), row("A", "NO_RESPONSE", 9.0)], key=pool_sort_key)],
          ["A", "B"])
    check("a rank bucket still outranks an answer",
          [r["display_name"] for r in sorted([{**row("Below", "AVAILABLE", 0.0), "squad_match": False, "tier": 2},
                                              row("Own", "NO_RESPONSE", 0.0)], key=pool_sort_key)],
          ["Own", "Below"])

    def two_day(name, availability, w1, w2, score=0.0):
        return {**row(name, availability, score),
                "availability_days": [{"date": "d1", "status": w1}, {"date": "d2", "status": w2}]}
    check("half-available (either way) leads its bucket: above Available, Maybe and no answer, whatever the form",
          [r["display_name"] for r in sorted([
              row("Silent Star", "NO_RESPONSE", 90.0),
              two_day("W2 Only", "UNAVAILABLE", "UNAVAILABLE", "AVAILABLE", 0.0),
              two_day("W1 Only", "UNAVAILABLE", "AVAILABLE", "UNAVAILABLE", 0.0),
              row("Maybe Low", "MAYBE", 1.0), row("Avail Low", "AVAILABLE", 0.0)], key=pool_sort_key)],
          ["W1 Only", "W2 Only", "Avail Low", "Maybe Low", "Silent Star"])

    check("half_open leads the pool, squad order kept inside it",
          [r["display_name"] for r in sorted([
              {**two_day("Half Below", "UNAVAILABLE", "AVAILABLE", "UNAVAILABLE"), "half_open": True, "squad_match": False, "tier": 2},
              {**two_day("Half Own", "UNAVAILABLE", "UNAVAILABLE", "AVAILABLE"), "half_open": True},
              row("Own Avail", "AVAILABLE", 99.0), row("Own Silent", "NO_RESPONSE", 0.0)], key=pool_sort_key)],
          ["Half Own", "Half Below", "Own Avail", "Own Silent"])

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

    print("\n# E. Squads with no rank of their own (OD sides all guessed to the same default)")
    od = {}
    async with Session() as db:
        for n in ("OD1 Gold", "OD2 Gold", "OD3 Gold", "OD6 Gold", "OD10 Blue"):
            g, t = uuid.uuid4(), uuid.uuid4()
            db.add(Grade(id=g, season_id=season_id, name=n, match_formats=["one_day"], categories=["senior"]))
            await db.flush()
            db.add(Team(id=t, organisation_id=org_id, name=n, sequence=50, grade_id=g))
            G[n], T[n], od[n] = g, t, n
        await db.commit()
    fx6 = await fixture("OD6 Gold", on=d + timedelta(days=28))
    async def avail_on(pid_, status, on):
        async with Session() as db:
            await db.execute(text(
                "INSERT INTO player_availability (organisation_id, player_id, avail_date, status) "
                "VALUES (:o, :p, :d, :s)"), {"o": org_id, "p": pid_, "d": on, "s": status})
            await db.commit()
    on6 = d + timedelta(days=28)
    od10 = await player("Od Ten", ["OD10 Blue"])
    od6 = await player("Od Six", ["OD6 Gold"])
    od3 = await player("Od Three", ["OD3 Gold"])
    od2 = await player("Od Two", ["OD2 Gold"])
    od1 = await player("Od One", ["OD1 Gold"])
    od6_noresp = await player("Od Six NoResponse", ["OD6 Gold"])
    od3_noresp = await player("Od Three NoResponse", ["OD3 Gold"])
    for p_ in (od10, od6, od3, od2, od1):
        await avail_on(p_, "AVAILABLE", on6)
    rows6 = await pool(fx6)
    o6 = [r["display_name"] for r in rows6]
    i6 = lambda n: o6.index(n) if n in o6 else 10_000
    check("OD1 above OD2 above OD3", i6("Od One") < i6("Od Two") < i6("Od Three"), True)
    check("OD3 above OD6 Gold (own squad), though all share sequence 50", i6("Od Three") < i6("Od Six"), True)
    check("OD6 Gold available above OD10 Blue available (numbers read as numbers)", i6("Od Six") < i6("Od Ten"), True)
    check("every available OD player comes before any no-answer player", max(i6(n) for n in ("Od One", "Od Two", "Od Three", "Od Six", "Od Ten")) < min(i6("Od Six NoResponse"), i6("Od Three NoResponse")), True)
    check("OD6 Gold's own no-answer player sorts first of those left", i6("Od Six NoResponse") < i6("Od Three NoResponse"), True)

    print("\n# F. A two-day game: free one weekend only leads the pool (real route)")
    on_a = d + timedelta(days=35)
    on_b = on_a + timedelta(days=7)
    fid2 = uuid.uuid4()
    async with Session() as db:
        db.add(Fixture(id=fid2, organisation_id=org_id, grade_id=G["4th XI"], team_id=T["4th XI"],
                       source="manual", played_on=on_a, end_on=on_b, start_time="13:00",
                       status="UPCOMING", label="4th XI two-day"))
        await db.commit()
    w1 = await player("Half W1 Only", ["5th XI"])
    w2 = await player("Half W2 Only", ["5th XI"])
    w2_picked = await player("Half W2 Picked", ["5th XI"])
    both = await player("Both Weeks", ["4th XI"])
    silent = await player("Silent Four", ["4th XI"])
    for pid_, a_, b_ in ((w1, "AVAILABLE", "UNAVAILABLE"), (w2, "UNAVAILABLE", "AVAILABLE"),
                         (w2_picked, "UNAVAILABLE", "AVAILABLE"), (both, "AVAILABLE", "AVAILABLE")):
        await avail_on(pid_, a_, on_a)
        await avail_on(pid_, b_, on_b)
    await name_in_xi(fid2, w2_picked)
    rows_f = await pool(fid2)
    of = [r["display_name"] for r in rows_f]
    bf = {r["display_name"]: r for r in rows_f}
    check("W1 only and W2 only are half_open", (bf["Half W1 Only"].get("half_open"), bf["Half W2 Only"].get("half_open")), (True, True))
    check("a full yes and a silent player are not", (bf["Both Weeks"].get("half_open"), bf["Silent Four"].get("half_open")), (False, False))
    check("one already in the XI is not half_open", bf["Half W2 Picked"].get("half_open"), False)
    check("availability stays the combined answer", bf["Half W2 Only"].get("availability"), "UNAVAILABLE")
    check("both half players lead, ahead of a full yes in the own squad",
          sorted(of[:2]), ["Half W1 Only", "Half W2 Only"])
    check("the full yes follows them, then the silent player", of.index("Both Weeks") < of.index("Silent Four"), True)
    check("one-day game: nobody is half_open", [n for n, r in r2.items() if r.get("half_open")], [])

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        print("\n".join(base.FAILURES))
        sys.exit(1)


asyncio.run(main())
