"""Verification: a player checks themselves in to nets from their own page, and
sees where and when they bat, against a real Postgres.

Asked for: on the player dashboard a player can check themselves in to a net
session, is put in the batting order, and sees their place: which net, and what
time they bat (time-slot session), or how many are ahead of them (queue).

Drives the SHIPPED route bodies (`public_availability.get_my_profile`,
`get_my_nets`, `check_in_to_nets`) and the shared writer behind them, never a
re-implementation:

  * the page lists tonight's sessions with a check-in offer; the profile carries it
  * checking in puts a time-slot player in their squad's net at the first slot
    that has not started, and tells them the net, the clock time and the moment
    that slot starts, plus any second-go times
  * a queue session puts them at the back and says how many are ahead; the first
    `nets` people read "in the nets now", the rest do not
  * a repeat tap changes nothing; a coach-placed player sees their place with no
    self check-in at all
  * a session limited to other squads is not offered; an ended one, an old one
    and another club's are never offered
  * a club with self check-in off gets a refusal, not a button (and a player the
    coach checked in still sees their place)
  * no cookie is refused; the payload carries counts, never other people
  * the coach's screen sees the arrival as a self check-in

CONTROL MODE: against the previous commit the new routes and keys are absent;
they are read through presence-safe accessors so the control reports failed
checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_net_player_page.py
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException
from sqlalchemy import text

import verify_net_checkin as base
from app.models.db import NetSession, Organisation, Player, Team, User

check = base.check
Session = base.Session


async def main():
    import app.routers.net_manager as nm
    import app.routers.public_availability as pa

    await base.build_schema()
    ddl_ok = True
    try:
        for mod in ("net_session_link_ddl", "net_slots_ddl"):
            ddl = importlib.import_module(f"app.services.{mod}")
            async with base.engine.begin() as conn:
                for stmt in ddl.STATEMENTS:
                    await conn.execute(text(stmt))
    except ImportError:
        ddl_ok = False
    ids = await base.seed()
    jack, brad, graeme = ids["players"]
    TOK = "tok-player-page"
    TODAY = datetime.now(timezone.utc).date()
    PINNED = [datetime(TODAY.year, TODAY.month, TODAY.day, 7, 0, tzinfo=timezone.utc)]   # 3pm Perth
    nm._utcnow = lambda: PINNED[0]

    async def guarded(label, fn):
        try:
            await fn()
        except Exception as ex:  # noqa: BLE001
            base.FAIL += 1
            print(f"  FAIL {label}: step could not run ({type(ex).__name__}: {str(ex)[:110]})")

    async def as_admin(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            user = await db.get(User, ids["user"])
            try:
                return await fn(*a, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e

    async def as_reader(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            return await fn(*a, db=db, club=club, **kw)

    def req_for(pid):
        resp = base.FakeResponse()
        pa._issue_cookie(resp, ids["club"], pid)
        return base.FakeRequest(cookies=dict(resp.cookies))

    async def profile(pid):
        async with Session() as db:
            return await pa.get_my_profile(TOK, req_for(pid), None, db)

    async def nets_of(pid):
        async with Session() as db:
            return await pa.get_my_nets(TOK, req_for(pid), db)

    async def self_checkin(pid, sid, cookie=True):
        async with Session() as db:
            try:
                req = req_for(pid) if cookie else base.FakeRequest()
                return await pa.check_in_to_nets(TOK, str(sid), req, db), None
            except HTTPException as e:
                return None, e

    def session_in(payload, sid):
        for s in (payload or {}).get("sessions", payload.get("nets", []) if isinstance(payload, dict) else []):
            if s["id"] == str(sid):
                return s
        return None

    async def set_org(**kw):
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            for k, v in kw.items():
                setattr(club, k, v)
            await db.commit()

    await set_org(availability_link_token=TOK, availability_self_service_enabled=True, net_checkin_enabled=True)

    seniors, colts = uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Team(id=seniors, organisation_id=ids["club"], name="Seniors", short_name="1st", sequence=1))
        db.add(Team(id=colts, organisation_id=ids["club"], name="Colts", short_name="3rd", sequence=2))
        await db.flush()
        for t, p in ((seniors, jack), (seniors, brad), (colts, graeme)):
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": t, "p": p, "o": ids["club"]})
        # Another club's session, an ended one and an old one: never offered.
        other_s = NetSession(id=uuid.uuid4(), organisation_id=ids["other"], session_date=TODAY, label="Their nets", status="active", version=0)
        ended_s = NetSession(id=uuid.uuid4(), organisation_id=ids["club"], session_date=TODAY, label="Finished", status="done", version=0)
        old_s = NetSession(id=uuid.uuid4(), organisation_id=ids["club"], session_date=TODAY - timedelta(days=9), label="Last week", status="active", version=0)
        db.add_all([other_s, ended_s, old_s])
        await db.commit()

    auto_id = queue_id = colts_only_id = None

    print("\n── Tonight's nets are offered on the page ──")
    async def step_1():
        nonlocal auto_id, queue_id, colts_only_id
        r, _ = await as_admin(nm.create_session, nm.SessionCreate(
            session_date=TODAY, label="Tuesday nets", mode="auto", slot_plan={"tz_offset_minutes": 480}))
        auto_id = r["id"]
        await as_admin(nm.put_slot_plan, auto_id, nm.SlotPlanBody(
            first_time="16:45", slot_minutes=7, finish_time="18:09", second_go=True, tz_offset_minutes=480,
            nets=[{"id": "n1", "name": "1st & 2nd XI", "squad_team_ids": [str(seniors)]},
                  {"id": "n2", "name": "3rd & 4th XI", "squad_team_ids": [str(colts)]}]))
        r, _ = await as_admin(nm.create_session, nm.SessionCreate(session_date=TODAY, label="Colts only", squad_team_ids=[str(colts)]))
        colts_only_id = r["id"]
        p = await profile(jack)
        s = session_in({"sessions": p.get("nets", [])}, auto_id)
        check("the profile carries tonight's nets", s is not None, True)
        check("with a check-in offer", (s or {}).get("can_check_in"), True)
        check("and no place yet", (s or {}).get("checked_in"), False)
        check("a session for another squad is not offered to a senior", session_in({"sessions": p.get("nets", [])}, colts_only_id), None)
        offered = {x["id"] for x in p.get("nets", [])}
        check("an ended session, an old one and another club's are never offered",
              offered.isdisjoint({str(ended_s.id), str(old_s.id), str(other_s.id)}), True)
        n = await nets_of(jack)
        check("the nets poll returns the same sessions", {x["id"] for x in n["sessions"]}, offered)
    await guarded("Tonight's nets are offered", step_1)

    print("\n── Checking in places a time-slot player ──")
    async def step_2():
        res, err = await self_checkin(jack, auto_id)
        s = session_in(res, auto_id)
        pl = (s or {}).get("place") or {}
        check("the check-in is accepted", (res or {}).get("added"), 1)
        check("they are in their squad's net", (pl.get("net") or {}).get("name"), "1st & 2nd XI")
        check("with the clock time of the first slot (nothing has started)", pl.get("time"), "16:45")
        check("and the absolute moment it starts (08:45Z = 4:45pm Perth)", (pl.get("start_at") or "")[11:16], "08:45")
        check("second-go times are listed for the free slots at the foot", (pl.get("also") or [None])[0], "16:52")
        again, _ = await self_checkin(jack, auto_id)
        check("a repeat tap changes nothing", (again or {}).get("added"), 0)
        p = await profile(jack)
        s2 = session_in({"sessions": p["nets"]}, auto_id)
        check("the page now shows checked in, no offer", ((s2 or {}).get("checked_in"), (s2 or {}).get("can_check_in")), (True, False))
        live = await as_reader(nm.get_session, auto_id)
        arrivals = {a["name"]: a["source"] for a in live["attendees"]}
        check("the coach's screen sees them as a self check-in", sorted(set(arrivals.values())), ["self"])
        PINNED[0] = datetime(TODAY.year, TODAY.month, TODAY.day, 8, 50, tzinfo=timezone.utc)      # 4:50pm Perth, the nets have started
        p = await profile(brad)
        s3 = session_in({"sessions": p["nets"]}, auto_id)
        check("once the nets have started the page says so and offers no button", ((s3 or {}).get("started"), (s3 or {}).get("can_check_in")), (True, False))
        res, err = await self_checkin(brad, auto_id)
        check("and a check-in from the page is refused with 409", getattr(err, "status_code", None), 409)
        check("saying why, in words", "have started" in str(getattr(err, "detail", "")), True)
        r, _ = await as_admin(nm.add_attendee, auto_id, nm.AttendeeAdd(player_id=str(brad)))
        late = next(a for a in r["attendees"] if a["player_id"] == str(brad))
        check("the coach can still check a latecomer in: the next slot that has not started (4:52)", (late["net_key"], late["slot_index"]), ("n1", 1))
        pl = (session_in({"sessions": (await profile(brad))["nets"]}, auto_id) or {}).get("place") or {}
        check("and the page then shows their place", pl.get("time"), "16:52")
        live = await as_reader(nm.get_session, auto_id)
        check("and the grid has them where the page says", [(c["attendee_id"] is not None and not c["repeat"]) for c in live["grid"]["nets"][0]["cells"][:3]], [True, True, False])
        PINNED[0] = datetime(TODAY.year, TODAY.month, TODAY.day, 7, 0, tzinfo=timezone.utc)
    await guarded("Checking in places a time-slot player", step_2)

    print("\n── A coach-placed player sees their place ──")
    async def step_3():
        r, _ = await as_admin(nm.add_attendee, auto_id, nm.AttendeeAdd(player_id=str(graeme)))
        p = await profile(graeme)
        s = session_in({"sessions": p["nets"]}, auto_id)
        check("a player the coach checked in sees their net", (((s or {}).get("place") or {}).get("net") or {}).get("name"), "3rd & 4th XI")
        check("and is not offered a second check-in", (s or {}).get("can_check_in"), False)
        leak = set(((s or {}).get("place") or {}).keys())
        check("the place says nothing about anyone else", leak.isdisjoint({"attendees", "names", "grid", "others"}), True)
        # A player the coach set to not batting.
        att = next(a for a in r["attendees"] if a["player_id"] == str(graeme))
        await as_admin(nm.patch_attendee, auto_id, att["id"], nm.AttendeePatch(bats=False))
        p = await profile(graeme)
        pl = (session_in({"sessions": p["nets"]}, auto_id) or {}).get("place") or {}
        check("sitting out is said as such, with no net or time", (pl.get("bats"), pl.get("net"), pl.get("time")), (False, None, None))
    await guarded("A coach-placed player", step_3)

    print("\n── A queue session: position in the batting order ──")
    async def step_4():
        nonlocal queue_id
        # The auto session would also be offered: end it so this reads clean.
        await as_admin(nm.update_session, auto_id, nm.SessionUpdate(status="done"))
        await as_admin(nm.delete_session, colts_only_id)
        r, _ = await as_admin(nm.create_session, nm.SessionCreate(session_date=TODAY, label="Queue night", settings={"nets": 2, "duration_seconds": 600}))
        queue_id = r["id"]
        out = {}
        for key, pid in (("jack", jack), ("brad", brad), ("graeme", graeme)):
            res, _ = await self_checkin(pid, queue_id)
            out[key] = (session_in(res, queue_id) or {}).get("place") or {}
        check("the first in the queue is first with nobody ahead", (out["jack"].get("position"), out["jack"].get("ahead")), (1, 0))
        check("the second is second with one ahead", (out["brad"].get("position"), out["brad"].get("ahead")), (2, 1))
        p = await profile(jack)
        s = session_in({"sessions": p["nets"]}, queue_id)
        check("the first two are in the nets now (2 nets), the third is not",
              [out["jack"].get("in_nets_now"), out["brad"].get("in_nets_now"), out["graeme"].get("in_nets_now")], [True, True, False])
        check("the queue says how many are waiting, as a count", ((s or {}).get("place") or {}).get("waiting"), 3)
        r, err = await as_admin(nm.rotate_group, queue_id, nm.RotateBody(autostart=False, turn_seq=0))
        res = {k: ((session_in({"sessions": (await profile(pid))["nets"]}, queue_id) or {}).get("place") or {}) for k, pid in (("jack", jack), ("brad", brad), ("graeme", graeme))}
        check("after a rotation the first two have had their turn", (res["jack"].get("batted"), res["brad"].get("batted")), (True, True))
        check("and the third is now in the nets", (res["graeme"].get("in_nets_now"), res["graeme"].get("position")), (True, 1))
    await guarded("A queue session", step_4)

    print("\n── Switches and cookies ──")
    async def step_5():
        await set_org(net_checkin_enabled=False)
        p = await profile(jack)
        s = session_in({"sessions": p["nets"]}, queue_id)
        check("with self check-in off a player already in still sees their place", ((s or {}).get("checked_in"), ((s or {}).get("place") or {}).get("batted")), (True, True))
        await as_admin(nm.update_session, queue_id, nm.SessionUpdate(status="active"))
        fresh = uuid.uuid4()
        async with Session() as db:
            db.add(Player(id=fresh, organisation_id=ids["club"], name="Fresh, Fran", status="active", is_player=True))
            await db.commit()
        p = await profile(fresh)
        s = session_in({"sessions": p["nets"]}, queue_id)
        check("and a player not in it is offered no button", (s or {}).get("can_check_in"), False)
        res, err = await self_checkin(fresh, queue_id)
        check("a check-in is refused with 403", getattr(err, "status_code", None), 403)
        await set_org(net_checkin_enabled=True)
        res, err = await self_checkin(fresh, queue_id, cookie=False)
        check("no cookie is refused with 401", getattr(err, "status_code", None), 401)
        res, err = await self_checkin(fresh, str(uuid.uuid4()))
        check("a session that is not on is refused with 409", getattr(err, "status_code", None), 409)
        res, err = await self_checkin(fresh, other_s.id)
        check("another club's session is refused with 409", getattr(err, "status_code", None), 409)
        res, err = await self_checkin(fresh, queue_id)
        check("and with the switch back on the same player can check in", (res or {}).get("added"), 1)
    await guarded("Switches and cookies", step_5)

    print(f"\n{'='*60}\n{base.PASS} passed, {base.FAIL} failed")
    if base.FAILURES:
        print("\nFailures:")
        for f in base.FAILURES:
            print("  -", f)
    await base.engine.dispose()
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
