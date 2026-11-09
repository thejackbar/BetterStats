"""Verification: nets run as a GRID of time slots, against a real Postgres.

Asked (North Perth): the club runs nets from a sheet, one column per net and one
row per seven-minute slot, and its people follow that better than the batting
queue. Wanted: when a session is set up, choose manual (the queue) or automatic;
automatic means nets named for squads, a first net time, and each person placed
in their squad's net as they check in.

Drives the SHIPPED route bodies (`create_session`, `put_slot_plan`,
`add_attendee`, `move_slot`, `patch_attendee`, `remove_attendee`,
`update_session`), never a re-implementation:

  * a new auto session starts unconfigured; the plan drops another club's squad
  * check-in gives each person a net by squad, a player in two squads goes to
    the HIGHER one, guests and unsquadded players go to the catch-all net
  * a repeat check-in changes nothing
  * a late arrival takes the first slot that has NOT started, not a gap behind
  * a drag onto an occupied cell swaps; onto an empty one just moves; both are
    manual and survive a re-plan; changing the slot length moves only the times
  * someone sitting out frees their cell and coming back takes a new one
  * a finish time with too many people flags who does not fit; extending it
    seats them again, in check-in order
  * second go repeats a net's order in the free slots at its foot, derived
  * with no catch-all, a guest is "not in a net" until placed by hand
  * six phones checking in at once never share a cell (the unique index)
  * a manual session is untouched: no net, no slot, no grid
  * the DDL is idempotent and its downgrade works

CONTROL MODE: against the previous commit the new routes, columns and keys are
absent; they are read through presence-safe accessors so the control reports
failed checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_net_time_slots.py
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException
from sqlalchemy import text

import verify_net_checkin as base
from app.models.db import Organisation, Player, Team, User

check = base.check
Session = base.Session

DAY = date(2026, 11, 10)
# Perth is UTC+8: 16:45 local is 08:45Z.
T_EARLY = datetime(2026, 11, 10, 8, 0, tzinfo=timezone.utc)     # 4:00pm, before the first net
T_1650 = datetime(2026, 11, 10, 8, 50, tzinfo=timezone.utc)     # 4:50pm, inside slot 0
T_1720 = datetime(2026, 11, 10, 9, 20, tzinfo=timezone.utc)     # 5:20pm, exactly slot 5
PINNED = [T_EARLY]


async def main():
    import app.routers.net_manager as nm

    nm._utcnow = lambda: PINNED[0]          # the clock placement reads

    await base.build_schema()
    ddl = None
    try:
        link = importlib.import_module("app.services.net_session_link_ddl")
        async with base.engine.begin() as conn:
            for stmt in link.STATEMENTS:
                await conn.execute(text(stmt))
        ddl = importlib.import_module("app.services.net_slots_ddl")
        async with base.engine.begin() as conn:
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
    except ImportError:
        pass
    ids = await base.seed()
    jack, brad, graeme = ids["players"]

    async def guarded(label, fn):
        try:
            await fn()
        except Exception as ex:  # noqa: BLE001
            base.FAIL += 1
            print(f"  FAIL {label}: step could not run ({type(ex).__name__}: {str(ex)[:100]})")

    async def as_admin(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            user = await db.get(User, ids["user"])
            try:
                return await fn(*a, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e

    # Squads: Seniors (1st) and Colts (2nd). Jack is in BOTH.
    seniors, colts, foreign_team = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p4, p5 = uuid.uuid4(), uuid.uuid4()
    colts_kids = [uuid.uuid4() for _ in range(6)]
    async with Session() as db:
        db.add(Team(id=seniors, organisation_id=ids["club"], name="Seniors", short_name="1st", sequence=1))
        db.add(Team(id=colts, organisation_id=ids["club"], name="Colts", short_name="3rd", sequence=2))
        db.add(Team(id=foreign_team, organisation_id=ids["other"], name="Their 1st XI", sequence=1))
        for pid, nm_ in [(p4, "Late, Larry"), (p5, "Later, Lou")] + [(k, f"Kid{i}, Colt") for i, k in enumerate(colts_kids)]:
            db.add(Player(id=pid, organisation_id=ids["club"], name=nm_, status="active", is_player=True))
        await db.flush()
        for t, p in ((seniors, jack), (colts, jack), (seniors, brad), (colts, graeme), (seniors, p4), (seniors, p5)):
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": t, "p": p, "o": ids["club"]})
        for k in colts_kids:
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": colts, "p": k, "o": ids["club"]})
        await db.commit()

    sid = None

    def places(payload):
        return {a["player_id"] or a["name"]: (a.get("net_key"), a.get("slot_index")) for a in payload["attendees"]}

    def cell_of(payload, pid):
        return places(payload).get(str(pid))

    async def as_reader(fn, *a, **kw):
        """Read routes are gated by a decorator dependency and take no `user`."""
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            return await fn(*a, db=db, club=club, **kw), None

    async def checkin(pid=None, guest=None):
        body = nm.AttendeeAdd(player_id=str(pid)) if pid else nm.AttendeeAdd(guest_name=guest)
        r, e = await as_admin(nm.add_attendee, str(sid), body)
        return r if r is not None else {"attendees": [], "_err": e}

    async def live():
        r, _ = await as_reader(nm.get_session, str(sid))
        return r

    print("\n── A new automatic session, and its plan ──")
    async def step_1():
        nonlocal sid
        r, e = await as_admin(nm.create_session, nm.SessionCreate(
            session_date=DAY, label="Tuesday nets", mode="auto", slot_plan={"tz_offset_minutes": 480}))
        sid = r["id"]
        check("a session made in time-slot mode says so", r.get("mode"), "auto")
        check("with no times set the grid is not configured", (r.get("grid") or {}).get("configured"), False)
        plan = nm.SlotPlanBody(
            first_time="16:45", slot_minutes=7, finish_time="18:09", second_go=False,
            tz_offset_minutes=480,
            nets=[
                {"id": "n1", "name": "1st & 2nd XI", "squad_team_ids": [str(seniors), str(foreign_team)]},
                {"id": "n2", "name": "3rd & 4th XI", "squad_team_ids": [str(colts)]},
                {"id": "n3", "name": "Juniors / etc", "catch_all": True},
            ])
        r, e = await as_admin(nm.put_slot_plan, str(sid), plan)
        g = r["grid"]
        check("the plan makes the grid configured", g["configured"], True)
        check("twelve slots from 4:45 to 6:09 at seven minutes", g["slots"], 12)
        check("first and last slot times", (g["times"][0], g["times"][-1]), ("16:45", "18:02"))
        check("another club's squad is dropped from the plan", r["slot_plan"]["nets"][0]["squad_team_ids"], [str(seniors)])
        check("three nets come back in order", [n["name"] for n in g["nets"]], ["1st & 2nd XI", "3rd & 4th XI", "Juniors / etc"])
    await guarded("A new automatic session", step_1)

    print("\n── Check-in places people by squad ──")
    async def step_2():
        await checkin(jack)
        await checkin(brad)
        await checkin(graeme)
        r = await checkin(guest="Newcomer Nick")
        check("a player in two squads goes to the higher one's net (first slot)", cell_of(r, jack), ("n1", 0))
        check("the next senior takes the next slot", cell_of(r, brad), ("n1", 1))
        check("a colt goes to the colts' net", cell_of(r, graeme), ("n2", 0))
        check("a guest goes to the catch-all net", places(r).get("Newcomer Nick"), ("n3", 0))
        again = await checkin(jack)
        check("a repeat check-in changes nothing", (cell_of(again, jack), again["attendee_count"]), (("n1", 0), 4))
    await guarded("Check-in places people by squad", step_2)

    print("\n── A late arrival takes a slot that has not started ──")
    async def step_3():
        PINNED[0] = T_1650
        r = await checkin(p4)
        check("at 4:50 the next free slot that has not started is 4:59 (slot 2)", cell_of(r, p4), ("n1", 2))
        PINNED[0] = T_1720
        r = await checkin(p5)
        check("at 5:20 a latecomer gets 5:20, not an empty slot behind the clock", cell_of(r, p5), ("n1", 5))
        g = r["grid"]
        check("the grid still has the earlier people where they were", [c["attendee_id"] is not None for c in g["nets"][0]["cells"][:3]], [True, True, True])
    await guarded("A late arrival", step_3)

    print("\n── Dragging: swap, move, and what a re-plan leaves alone ──")
    async def step_4():
        PINNED[0] = T_EARLY
        r = await live()
        att = {a["player_id"]: a["id"] for a in r["attendees"] if a["player_id"]}
        r, e = await as_admin(nm.move_slot, str(sid), nm.SlotMove(attendee_id=att[str(p5)], net_id="n1", slot_index=0))
        check("dropping onto an occupied cell swaps the two", (cell_of(r, p5), cell_of(r, jack)), (("n1", 0), ("n1", 5)))
        check("both are now manual", [a["slot_manual"] for a in r["attendees"] if a["player_id"] in (str(p5), str(jack))], [True, True])
        r, e = await as_admin(nm.move_slot, str(sid), nm.SlotMove(attendee_id=att[str(graeme)], net_id="n1", slot_index=7))
        check("dropping onto an empty cell in another net just moves them", cell_of(r, graeme), ("n1", 7))
        r, e = await as_admin(nm.move_slot, str(sid), nm.SlotMove(attendee_id=att[str(graeme)], net_id="nope", slot_index=1))
        check("a net that is not in the plan is refused", getattr(e, "status_code", None), 422)
        r, e = await as_admin(nm.move_slot, str(sid), nm.SlotMove(attendee_id=att[str(graeme)], net_id="n1", slot_index=99))
        check("a slot past the finish is refused", getattr(e, "status_code", None), 422)
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(slot_minutes=10))
        check("changing the slot length keeps everyone where they are", (cell_of(r, p5), cell_of(r, jack), cell_of(r, graeme)), (("n1", 0), ("n1", 5), ("n1", 7)))
        check("...and moves only the times", r["grid"]["times"][1], "16:55")
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(slot_minutes=7))
        check("a net removed from the plan re-places its people in a net that exists",
              all(net in ("n1", "n2", "n3") for net, _ in places(r).values() if net), True)
    await guarded("Dragging", step_4)

    print("\n── Sitting out, and leaving ──")
    async def step_5():
        r = await live()
        att = {a["player_id"]: a["id"] for a in r["attendees"] if a["player_id"]}
        r, e = await as_admin(nm.patch_attendee, str(sid), att[str(brad)], nm.AttendeePatch(bats=False))
        check("someone sitting out holds no cell", cell_of(r, brad), (None, None))
        check("and is not counted as 'not in a net'", str(brad) not in [x for x in r["grid"]["no_net"]], True)
        r, e = await as_admin(nm.patch_attendee, str(sid), att[str(brad)], nm.AttendeePatch(bats=True))
        check("coming back takes a cell again", cell_of(r, brad)[0], "n1")
        taken = [v for v in places(r).values() if v[0] == "n1"]
        check("and no two people share a cell", len(taken), len(set(taken)))
        r, e = await as_admin(nm.remove_attendee, str(sid), att[str(p4)])
        check("leaving drops them from the grid", str(p4) in places(r), False)
    await guarded("Sitting out", step_5)

    print("\n── A finish time, overflow, and second go ──")
    async def step_6():
        PINNED[0] = T_1720
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(slot_minutes=10, finish_time="17:15"))
        g = r["grid"]
        check("three ten-minute slots fit before 5:15", g["slots"], 3)
        check("people who do not fit are flagged, not dropped", g["overflow_count"] > 0, True)
        check("they are still in the session (five here after Larry left)", r["attendee_count"], 5)
        check("each one flagged sits under their net's column", sum(len(n["overflow"]) for n in g["nets"]), g["overflow_count"])
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(slot_minutes=7, finish_time="18:09"))
        check("extending the finish seats everyone again", r["grid"]["overflow_count"], 0)
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(second_go=True))
        n3 = r["grid"]["nets"][2]["cells"]
        check("second go repeats a net's order in the free slots at its foot",
              (n3[0]["repeat"], n3[1]["repeat"], n3[1]["attendee_id"] == n3[0]["attendee_id"], n3[11]["repeat"]), (False, True, True, True))
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(second_go=False))
        check("with second go off the foot stays empty", any(c["repeat"] for n in r["grid"]["nets"] for c in n["cells"]), False)
    await guarded("A finish time", step_6)

    print("\n── No catch-all net: warn, do not refuse ──")
    async def step_7():
        PINNED[0] = T_EARLY
        keep = [{"id": "n1", "name": "1st & 2nd XI", "squad_team_ids": [str(seniors)]},
                {"id": "n2", "name": "3rd & 4th XI", "squad_team_ids": [str(colts)]}]
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(nets=keep))
        nick = next(a for a in r["attendees"] if a["name"] == "Newcomer Nick")
        check("a guest with nowhere to go is listed as not in a net", nick["id"] in r["grid"]["no_net"], True)
        check("and holds no cell", (nick["net_key"], nick["slot_index"]), (None, None))
        r, e = await as_admin(nm.move_slot, str(sid), nm.SlotMove(attendee_id=nick["id"], net_id="n2", slot_index=3))
        check("the coach can place them by hand", places(r).get("Newcomer Nick"), ("n2", 3))
        check("and they are no longer listed as unplaced", r["grid"]["no_net"], [])
        r, e = await as_admin(nm.put_slot_plan, str(sid), nm.SlotPlanBody(nets=keep + [{"id": "n3", "name": "Juniors", "catch_all": True}]))
        check("a hand placement survives a later plan change", places(r).get("Newcomer Nick"), ("n2", 3))
    await guarded("No catch-all", step_7)

    print("\n── Six phones at once never share a cell ──")
    async def step_8():
        PINNED[0] = T_EARLY
        results = await asyncio.gather(*[as_admin(nm.add_attendee, str(sid), nm.AttendeeAdd(player_id=str(k))) for k in colts_kids])
        r = await live()
        mine = [places(r).get(str(k)) for k in colts_kids]
        check("all six are placed in the colts' net", all(m and m[0] == "n2" for m in mine), True)
        slots = [m[1] for m in mine if m]
        check("with six different slots", len(set(slots)), 6)
        check("and none of the six was told they were already in", all(res[1] is None for res in results), True)
        async with Session() as db:
            n = (await db.execute(text(
                "SELECT count(*) FROM (SELECT net_key, slot_index FROM net_attendance WHERE session_id = :s "
                "AND net_key IS NOT NULL AND slot_index IS NOT NULL GROUP BY 1,2 HAVING count(*) > 1) x"), {"s": sid})).scalar()
        check("the table holds no cell twice", n, 0)
        try:
            async with base.engine.begin() as conn:
                await conn.execute(text(
                    "INSERT INTO net_attendance (id, session_id, organisation_id, guest_name, net_key, slot_index) "
                    "SELECT gen_random_uuid(), session_id, organisation_id, 'dup', net_key, slot_index FROM net_attendance "
                    "WHERE session_id = :s AND net_key IS NOT NULL AND slot_index IS NOT NULL LIMIT 1"), {"s": sid})
            check("the unique index refuses a second person in a cell", False)
        except Exception:
            check("the unique index refuses a second person in a cell", True)
    await guarded("Six phones", step_8)

    print("\n── A manual session is untouched, and can be switched ──")
    async def step_9():
        r, e = await as_admin(nm.create_session, nm.SessionCreate(session_date=DAY, label="Queue night"))
        msid = r["id"]
        check("the default is manual", r.get("mode"), "manual")
        check("a manual session has no grid", r.get("grid"), None)
        r, e = await as_admin(nm.add_attendee, msid, nm.AttendeeAdd(player_id=str(jack)))
        check("a manual check-in gets no net or slot", cell_of(r, jack), (None, None))
        r, e = await as_admin(nm.update_session, msid, nm.SessionUpdate(mode="auto"))
        check("it can be switched to time slots", r.get("mode"), "auto")
        check("switching does not delete anyone", r["attendee_count"], 1)
        r, e = await as_admin(nm.put_slot_plan, msid, nm.SlotPlanBody(
            first_time="17:00", nets=[{"id": "a", "name": "Net A", "squad_team_ids": [str(seniors)]}]))
        check("setting the plan then places the people already there", cell_of(r, jack), ("a", 0))
        r, e = await as_admin(nm.update_session, msid, nm.SessionUpdate(mode="manual"))
        r2, e2 = await as_admin(nm.put_slot_plan, msid, nm.SlotPlanBody(first_time="17:00"))
        check("a manual session refuses a plan", getattr(e2, "status_code", None), 409)
        lst, _ = await as_reader(nm.list_sessions, limit=40)
        check("the session list says which mode each runs", sorted({s.get("mode") for s in lst["sessions"]}), ["auto", "manual"])
    await guarded("Manual untouched", step_9)

    print("\n── The DDL ──")
    async def step_10():
        async with base.engine.begin() as conn:
            for stmt in ddl.STATEMENTS + ddl.STATEMENTS:
                await conn.execute(text(stmt))
        check("every statement is safe to run twice", True)
        async with base.engine.begin() as conn:
            for stmt in ddl.DOWNGRADE:
                await conn.execute(text(stmt))
            cols = (await conn.execute(text(
                "SELECT count(*) FROM information_schema.columns WHERE table_name IN ('net_sessions','net_attendance') "
                "AND column_name IN ('mode','slot_plan','net_key','slot_index','slot_manual')"))).scalar()
            check("the downgrade removes only what this change added", cols, 0)
            tbl = (await conn.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_name IN ('net_sessions','net_attendance')"))).scalar()
            check("and leaves both tables in place", tbl, 2)
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
    await guarded("The DDL", step_10)

    print(f"\n{'='*60}\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAILURES:
        print("\nFailures:")
        for f in base.FAILURES:
            print("  -", f)
    await base.engine.dispose()
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
