"""Verification: the Audit History trail, against a real Postgres.

Asked for (Gisborne): a side-menu Audit History with a full trail of players moved
between squads, moved up and down a batting order, made captain or wicket-keeper,
and any other change to a player in selection, availability and squads, each with
time, date and who made it; searchable, filterable, exportable as CSV. And: a club
can switch "Maybe" off for availability.

Drives the SHIPPED route bodies and services (`set_selection`, `lock_selection`,
`set_availability`, `create_team`/`update_team`, the squad membership helpers, the
audit router), never a re-implementation.

CONTROL MODE: against the previous commit `app.services.player_audit` does not
exist; it is imported inside a guard and every read is presence-safe, so the control
FAILS the checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_audit_history.py
"""
from __future__ import annotations

import asyncio
import csv
import importlib
import inspect
import io
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
from app.models.db import Fixture, Grade, Organisation, Player, Season, Team, User

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
        for mod in ("selection_lock_ddl", "team_sides_ddl", "fixture_side_ddl", "fixture_pin_ddl", "audit_ddl", "availability_maybe_ddl"):
            try:
                for stmt in importlib.import_module(f"app.services.{mod}").STATEMENTS:
                    await conn.execute(text(stmt))
            except ImportError:
                pass
    try:
        pa = importlib.import_module("app.services.player_audit")
    except ImportError:
        pa = None
    import app.routers.selection as sel
    import app.routers.availability as av
    import app.routers.teams as teams_r
    from app.services import squad_membership as sm
    audit_r = None
    try:
        audit_r = importlib.import_module("app.routers.audit")
    except ImportError:
        pass

    org, other_org, uid, uid2, season = (uuid.uuid4() for _ in range(5))
    g1, t1, t2, F1 = (uuid.uuid4() for _ in range(4))
    P = [uuid.uuid4() for _ in range(7)]
    d0 = date.today() + timedelta(days=9)
    async with Session() as db:
        db.add(Organisation(id=org, name="Audit CC", slug=f"aud-{org.hex[:8]}"))
        db.add(Organisation(id=other_org, name="Other CC", slug=f"oth-{other_org.hex[:8]}"))
        db.add(User(id=uid, username=f"u{uid.hex[:8]}", email=f"{uid.hex[:8]}@x.com", password_hash="x", display_name="Sam Selector"))
        db.add(User(id=uid2, username=f"v{uid2.hex[:8]}", email=f"{uid2.hex[:8]}@x.com", password_hash="x", display_name="Pat Admin"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g1, season_id=season, name="1st Grade", categories=["senior"]))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="MACs", sequence=1, grade_id=g1))
        db.add(Team(id=t2, organisation_id=org, name="Thirds", sequence=3))
        await db.flush()
        for i, pid in enumerate(P):
            db.add(Player(id=pid, organisation_id=org, name=f"Player {i}", gender="male", is_player=True, status="active"))
        await db.flush()
        db.add(Fixture(id=F1, organisation_id=org, grade_id=g1, team_id=t1, source="manual", played_on=d0,
                       status="UPCOMING", opponent_name="Rovers", label="1st", round="1st"))
        await db.commit()

    def actor(user):
        if pa:
            pa.set_actor(user)

    async def as_user(fn, *args, user_id=uid, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            actor(user)
            who = "user" if "user" in inspect.signature(fn).parameters else "_user"
            try:
                return await fn(*args, db=db, club=club, **{who: user}, **kw), None
            except HTTPException as e:
                return None, e

    async def confirm(pids, cap=None, wk=None, lock=None):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, uid)
            actor(user)
            kw = {} if lock is None else {"lock": lock}
            body = sel.LineupSet(players=[
                sel.LineupSlot(player_id=str(p), batting_order=i + 1, is_captain=(p == cap), is_wicket_keeper=(p == wk))
                for i, p in enumerate(pids)], **kw)
            try:
                return await sel.set_selection(str(F1), body, db, club, user), None
            except HTTPException as e:
                return None, e

    async def events(**kw):
        if audit_r is None or pa is None:
            return {"events": [], "total": 0}
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, uid)
            return await audit_r.audit_events(db=db, club=club, _user=user, limit=200, offset=0,
                                              **{k: kw.get(k) for k in ("q", "area", "action", "user", "player_id", "team", "date_from", "date_to", "tz")})

    def acts(res, action):
        return [e for e in res["events"] if e["action"] == action]

    print("\n# A. Selection: every move of a player is its own line")
    await confirm(P[:5])
    r = await events(area="selection")
    check("naming five players logs five 'added to the XI' lines", len(acts(r, "added_to_xi")), 5)
    check("...each by the selector, with the game", all(e["by"] == "Sam Selector" and "Rovers" in (e["game"] or "") for e in acts(r, "added_to_xi")), True)
    await confirm([P[0], P[4], P[1], P[2], P[3]])
    r = await events(action="batting_order_changed")
    moved = acts(r, "batting_order_changed")
    check("one player jumping from 5 to 2 is ONE line, not four", len(moved), 1)
    check("...saying who, which way and where from and to", (moved[0]["player"], moved[0]["detail"].get("direction"), moved[0]["detail"].get("from"), moved[0]["detail"].get("to")) if moved else None, ("Player 4", "up", 5, 2))
    check("...in plain words", "moved up the batting order from no. 5 to no. 2" in (moved[0]["summary"] if moved else ""), True)
    await confirm([P[0], P[4], P[1], P[2], P[3]], cap=P[1], wk=P[2])
    r = await events(area="selection")
    check("making Player 1 captain is a line", [e["player"] for e in acts(r, "made_captain")], ["Player 1"])
    check("making Player 2 keeper is a line", [e["player"] for e in acts(r, "made_keeper")], ["Player 2"])
    await confirm([P[0], P[4], P[1], P[2], P[5]], cap=P[2], wk=P[2])
    r = await events(area="selection")
    check("a swap in and out logs both", ([e["player"] for e in acts(r, "removed_from_xi")], ([e["player"] for e in acts(r, "added_to_xi")] or [None])[0]), (["Player 3"], "Player 5"))
    check("the captain moving is a pair of lines", ([e["player"] for e in acts(r, "removed_captain")], ([e["player"] for e in acts(r, "made_captain")] or [None])[0]), (["Player 1"], "Player 2"))
    check("each confirmation is itself a line", len(acts(r, "side_confirmed")), 4)
    await as_user(sel.lock_selection, str(F1))
    await as_user(sel.unlock_selection, str(F1))
    r = await events(area="selection")
    check("locking and unlocking are lines", (len(acts(r, "side_locked")), len(acts(r, "side_unlocked"))), (1, 1))

    print("\n# B. Squads")
    async with Session() as db:
        actor(await db.get(User, uid2))
        await sm.add_squad_memberships(db, org, P[0], [t1], uid2)
        await db.commit()
    async with Session() as db:
        actor(await db.get(User, uid2))
        await sm.move_squad_membership(db, org, P[0], t1, t2, uid2)
        await db.commit()
    async with Session() as db:
        actor(await db.get(User, uid2))
        await sm.remove_squad_memberships(db, org, P[0], [t2])
        await db.commit()
    r = await events(area="squads")
    check("adding to a squad is a line", [e["summary"] for e in acts(r, "added_to_squad")], ["Player 0 added to MACs"])
    check("moving between squads is ONE line saying from and to", [e["summary"] for e in acts(r, "moved_squad")], ["Player 0 moved from MACs to Thirds"])
    check("removing from a squad is a line", [e["summary"] for e in acts(r, "removed_from_squad")], ["Player 0 removed from Thirds"])
    check("...by whoever acted (Pat Admin)", {e["by"] for e in r["events"] if e["action"] in ("added_to_squad", "moved_squad", "removed_from_squad")}, {"Pat Admin"})
    check("a move does not also log an add and a remove", (len(acts(r, "added_to_squad")), len(acts(r, "removed_from_squad"))), (1, 1))
    async with Session() as db:
        actor(await db.get(User, uid2))
        await sm.add_squad_memberships(db, org, P[0], [t1], uid2)
        await sm.add_squad_memberships(db, org, P[0], [t1], uid2)    # already in: nothing happened
        await db.commit()
    r = await events(area="squads")
    check("adding someone who is already in the squad logs nothing new", len(acts(r, "added_to_squad")), 2)
    club_user = None
    res, e = await as_user(teams_r.create_team, teams_r.TeamCreate(name="Fourths", sequence=4))
    res, e = await as_user(teams_r.update_team, str(t2), teams_r.TeamUpdate(short_name="3s"))
    r = await events(area="squads")
    check("creating and editing a squad are lines", (len(acts(r, "squad_created")), [e["summary"] for e in acts(r, "squad_updated")]), (1, ["Squad Thirds edited: short name"]))

    print("\n# C. Availability")
    on = d0
    item = lambda pid, status, note=None: av.AvailabilitySet(player_id=str(pid), date=on, status=status, note=note)  # noqa: E731
    await as_user(av.set_availability, item(P[1], "AVAILABLE"))
    await as_user(av.set_availability, item(P[1], "UNAVAILABLE", "away"))
    r = await events(area="availability")
    lines = [e["summary"] for e in acts(r, "availability_set")]
    check("each recorded answer is a line, newest first", len(lines), 2)
    check("...saying what it was before", any("marked Unavailable" in s_ and "(was Available)" in s_ and "away" in s_ for s_ in lines), True)
    if pa:
        async with Session() as db:
            actor(None)
            await av.audit_availability(db, org, P[2], on, None, "AVAILABLE", None, self_service=True)
            await db.commit()
    r = await events(area="availability")
    own = [e for e in acts(r, "availability_set") if e["player"] == "Player 2"]
    check("a player's own answer through their link names the player and says so", [(e["by"], e["via"]) for e in own], [("Player 2", "player link")])

    print("\n# D. Maybe can be switched off")
    res, e = await as_user(av.set_availability, item(P[3], "MAYBE"))
    check("Maybe is accepted while the club allows it", e is None, True)
    async with Session() as db:
        await db.execute(text("UPDATE organisations SET availability_allow_maybe = FALSE WHERE id = :o"), {"o": org})
        await db.commit()
    res, e = await as_user(av.set_availability, item(P[3], "AVAILABLE"))
    check("Available still works with Maybe off", e is None, True)
    res, e = await as_user(av.set_availability, item(P[4], "MAYBE"))
    check("Maybe is refused with Maybe off", getattr(e, "status_code", None), 400)
    res, e = await as_user(av.set_availability_bulk, av.AvailabilityBulk(items=[item(P[4], "AVAILABLE"), item(P[5], "MAYBE")]))
    check("a bulk update containing Maybe is refused", getattr(e, "status_code", None), 400)
    res, e = await as_user(av.create_period, av.PeriodCreate(player_id=str(P[4]), start_date=on, end_date=None, status="MAYBE"))
    check("a Maybe period is refused too", getattr(e, "status_code", None), 400)
    res, e = await as_user(av.set_availability, item(P[4], "NO_RESPONSE"))
    check("clearing an answer still works", e is None, True)
    async with Session() as db:
        club = await db.get(Organisation, org)
        cfg = await av.availability_config(club=club, user=None) if hasattr(av, "availability_config") else {}
        payload = await av._self_service_payload(db, club)
    check("the config route says Maybe is off", cfg.get("allow_maybe"), False)
    check("the link panel's settings say so too", payload.get("allow_maybe"), False)
    res, e = await as_user(av.update_self_service, av.SelfServiceUpdate(allow_maybe=True))
    check("the setting can be switched back on", (res or {}).get("allow_maybe"), True)
    res, e = await as_user(av.update_self_service, av.SelfServiceUpdate(show_squad=True))
    check("a PATCH that does not send it leaves it alone", (res or {}).get("allow_maybe"), True)

    print("\n# E. Search, filter, export")
    allr = await events()
    check("the list has everything, newest first", allr["total"] > 20 and allr["events"][0]["at"] >= allr["events"][-1]["at"], True)
    r = await events(q="Player 4")
    check("search finds a player by name", any(e["player"] == "Player 4" for e in r["events"]) and all("player" in (e["summary"] + (e["player"] or "")).lower() for e in r["events"]), True)
    r = await events(q="nobody-by-this-name")
    check("...and finds nothing for a name that is not there", r["total"], 0)
    r = await events(q="Player 2 captain")
    check("several words must all match", r["total"] > 0 and all("captain" in (e["summary"] + e["action"]).lower() for e in r["events"]), True)
    r = await events(user="Pat Admin")
    check("filtering by who made the change", r["total"] > 0 and {e["by"] for e in r["events"]} == {"Pat Admin"}, True)
    r = await events(area="squads")
    check("filtering by area", {e["area"] for e in r["events"]}, {"squads"})
    r = await events(action="moved_squad,made_captain")
    check("filtering by several actions", {e["action"] for e in r["events"]}, {"moved_squad", "made_captain"})
    r = await events(team="MACs")
    check("filtering by squad", r["total"] > 0 and all(e["team"] == "MACs" for e in r["events"]), True)
    r = await events(date_from=date.today().isoformat(), date_to=date.today().isoformat(), tz="UTC")
    check("filtering by date (today) keeps today's events", r["total"] == allr["total"], True)
    r = await events(date_to=(date.today() - timedelta(days=2)).isoformat(), tz="UTC")
    check("...and a range in the past finds none", r["total"], 0)
    r = await events(player_id=str(P[1]))
    check("filtering to one player", r["total"] > 0 and all(e["player_id"] == str(P[1]) for e in r["events"]), True)
    async with Session() as db:
        club = await db.get(Organisation, other_org)
        user = await db.get(User, uid)
        other = await audit_r.audit_events(db=db, club=club, _user=user, limit=50, offset=0, q=None, area=None, action=None, user=None, player_id=None, team=None, date_from=None, date_to=None, tz=None) if audit_r else {"total": 0}
    check("another club sees none of it", other["total"], 0)
    if audit_r and pa:
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, uid)
            page2 = await audit_r.audit_events(db=db, club=club, _user=user, limit=5, offset=5, q=None, area=None, action=None, user=None, player_id=None, team=None, date_from=None, date_to=None, tz=None)
            resp = await audit_r.audit_export(db=db, club=club, _user=user, q=None, area="squads", action=None, user=None, player_id=None, team=None, date_from=None, date_to=None, tz="Australia/Melbourne")
            fac = await audit_r.audit_facets(db=db, club=club, _user=user)
        check("pages of 5 come with the full total", (len(page2["events"]), page2["total"]), (5, allr["total"]))
        body = resp.body.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(body)))
        check("the CSV has a header row of ten columns", rows[0], ["Date", "Time", "Area", "Action", "Player", "Squad or team", "Game", "What changed", "Changed by", "Via"])
        sq_total = (await events(area="squads"))["total"]
        check("...and one row per matching event (same filters as the list)", len(rows) - 1, sq_total)
        check("...with the date, time, who and what", all(len(r_) == 10 and r_[0] and r_[1] and r_[8] for r_ in rows[1:]), True)
        check("...downloaded as a named csv", "audit-history.csv" in resp.headers.get("content-disposition", ""), True)
        check("facets offer who made changes and the squads", ("Pat Admin" in fac["users"], "MACs" in fac["teams"]), (True, True))
    else:
        check("the audit router exists", False)

    print("\n# F. Who is acting")
    check("get_current_user records the user for the shared writers", "set_actor" in (importlib.import_module("app.routers.auth").get_current_user.__code__.co_names), True)
    if pa:
        try:
            from httpx import ASGITransport, AsyncClient
            from fastapi import Depends, FastAPI
            app = FastAPI()

            async def dep():
                pa.set_actor(type("U", (), {"id": uid, "display_name": "Via Dep"})())

            @app.get("/x")
            async def x(_=Depends(dep)):
                return {"who": (pa.current_actor() or {}).get("name")}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://t") as c:
                got = (await c.get("/x")).json()
            check("a dependency's actor reaches the endpoint that runs after it", got, {"who": "Via Dep"})
        except ImportError:
            check("httpx is available for the dependency check", False)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
