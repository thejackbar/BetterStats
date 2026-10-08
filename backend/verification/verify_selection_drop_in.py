"""Verification: a player the squad above has not picked is offered, first, to the
grade below, against a real Postgres.

Reported: a 3rd XI squad player who had not been picked in the 3rds did not show
as a choice for the 4ths. He WAS in the pool, but as "tier 3" (one grade up),
which sorts behind every 4th and 5th squad player, so on a long list he was never
seen. The board's default order now puts a player the squad above has not taken
that day first, and labels him.

This drives the SHIPPED `assemble_selection` (the board's pool), never a
re-implementation:

  * 3rd XI squad, named in no XI that day     -> `drop_in_from` = "3rd XI", sorts FIRST in the 4ths
  * same player, named in the 3rds XI          -> no label (he is in the 3rds)
  * same player, marked unavailable            -> no label (marked out, shown as before)
  * same player, marked inactive               -> no label
  * same player, in the 3rds AND 4ths squads   -> no label (he is a 4ths player), tier 1
  * 5th XI squad (promotion)                   -> no label, behind the 4ths squad
  * 2nd XI squad (two grades up)               -> no label (not the grade directly above)
  * a fixture with no date                     -> no label (we cannot say "that day")
  * from the 3rds' own pool                    -> tier 1, no label

CONTROL MODE: run against the commit BEFORE this change. New keys are read
through `.get`, so the control reports the reported behaviour as failed checks
instead of crashing (rule 21).

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_drop_in.py
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
from app.models.db import (
    Organisation, User, Player, Team, Grade, Season, Fixture, FixtureLineup,
)

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
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

    fx3, fx4, fx5 = await fixture("3rd XI"), await fixture("4th XI"), await fixture("5th XI")

    jaimin = await player("Jaimin Major", ["3rd XI"])
    picked = await player("Picked In Threes", ["3rd XI"])
    out = await player("Out Of Threes", ["3rd XI"])
    gone = await player("Inactive Threes", ["3rd XI"], status="inactive")
    both = await player("Threes And Fours", ["3rd XI", "4th XI"])
    own = await player("Fours Regular", ["4th XI"])
    promo = await player("Fives Regular", ["5th XI"])
    twoup = await player("Seconds Regular", ["2nd XI"])
    await name_in_xi(fx3, picked)
    await avail(out, "UNAVAILABLE")

    # Everyone needs a recent game to be a normal pool member; the pool does not
    # hide anyone for lack of one, so give Jaimin a score-less history of none.
    rows = {r["display_name"]: r for r in await pool(fx4)}
    row = lambda n: rows.get(n) or {}

    print("\n# A. The 4ths' pool, 3rd XI squad player not picked in the 3rds")
    check("Jaimin is in the 4ths' pool", "Jaimin Major" in rows, True)
    check("Jaimin is one grade up (tier 3)", row("Jaimin Major").get("tier"), 3)
    check("Jaimin is labelled as not picked in the 3rd XI", row("Jaimin Major").get("drop_in_from"), "3rd XI")
    order = [r["display_name"] for r in await pool(fx4)]
    check("Jaimin sorts ahead of the 4ths' own squad", order.index("Jaimin Major") < order.index("Fours Regular"), True)
    check("Jaimin sorts ahead of the 5ths squad", order.index("Jaimin Major") < order.index("Fives Regular"), True)

    print("\n# B. Not labelled when there is a reason not to")
    check("named in the 3rds XI: no label", row("Picked In Threes").get("drop_in_from"), None)
    check("named in the 3rds XI: shown as a clash", bool(row("Picked In Threes").get("clash")), True)
    check("marked unavailable: no label", row("Out Of Threes").get("drop_in_from"), None)
    check("marked unavailable: still in the pool", "Out Of Threes" in rows, True)
    check("inactive: no label", row("Inactive Threes").get("drop_in_from"), None)
    check("in the 3rds AND 4ths squads: no label", row("Threes And Fours").get("drop_in_from"), None)
    check("in the 3rds AND 4ths squads: tier 1", row("Threes And Fours").get("tier"), 1)
    check("the 4ths' own squad: tier 1, no label", (row("Fours Regular").get("tier"), row("Fours Regular").get("drop_in_from")), (1, None))
    check("the 5ths squad: tier 2, no label", (row("Fives Regular").get("tier"), row("Fives Regular").get("drop_in_from")), (2, None))
    check("two grades up: no tier, no label", (row("Seconds Regular").get("tier"), row("Seconds Regular").get("drop_in_from")), (None, None))
    check("unavailable player does not jump the queue", order.index("Out Of Threes") > order.index("Fours Regular"), True)

    print("\n# C. Other fixtures")
    r3 = {r["display_name"]: r for r in await pool(fx3)}
    check("3rds' own pool: Jaimin is tier 1 with no label", (r3["Jaimin Major"].get("tier"), r3["Jaimin Major"].get("drop_in_from")), (1, None))
    r5 = {r["display_name"]: r for r in await pool(fx5)}
    check("5ths pool: Jaimin is two grades up, no label", r5["Jaimin Major"].get("drop_in_from"), None)
    fx_nodate = await fixture("4th XI", on=None)
    rn = {r["display_name"]: r for r in await pool(fx_nodate)}
    check("a fixture with no date: no label (cannot say 'that day')", rn["Jaimin Major"].get("drop_in_from"), None)

    print("\n# D. Picked in the 3rds AFTER: the label goes")
    late = await player("Late Pick", ["3rd XI"])
    check("before: labelled", {r["display_name"]: r for r in await pool(fx4)}["Late Pick"].get("drop_in_from"), "3rd XI")
    await name_in_xi(fx3, late)
    check("after being named in the 3rds: no label", {r["display_name"]: r for r in await pool(fx4)}["Late Pick"].get("drop_in_from"), None)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAIL:
        print("\n".join(base.FAILURES))
        sys.exit(1)


asyncio.run(main())
