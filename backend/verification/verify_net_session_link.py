"""Verification: a net session's OWN check-in link and the squads it is for,
against a real Postgres.

Reported (Gisborne): the net check-in link was one QR for the whole club, so a
code printed for one night checked people into every session that was open, and
the list was always the whole club. Wanted: a link that is unique to a session,
and check-in by squad.

Drives the SHIPPED route bodies (`create_session`, `update_session`, the
session-link routes, the public landing / verify / check-in), never a
re-implementation:

  * every new session gets its own token; two sessions never share one
  * a session's link checks a player into THAT session only; the club-wide link
    still joins every live session, exactly as before
  * a session limited to squads lists only those squads' members on its own link;
    an unlimited session beside it keeps the club-wide link's list whole
  * `squad_team_ids` follows the PATCH rule: left out = untouched, explicit
    empty = everyone; another club's team is never stored
  * an ended session's link is a dead end (no sessions, check-in refused)
  * regenerating one session's link kills only that link
  * a session made before this change gets its token the first time it is asked
  * the roster carries each player's squads so check-in can be done squad by squad

CONTROL MODE: against the previous commit the new routes, columns and keys are
absent; they are read through presence-safe accessors so the control reports
failed checks instead of crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_net_session_link.py
"""
from __future__ import annotations

import asyncio
import importlib
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi import HTTPException
from sqlalchemy import text

import verify_net_checkin as base
from app.models.db import Organisation, Player, Team, User

check = base.check
Session = base.Session


async def main():
    import app.routers.net_manager as nm
    import app.routers.public_net_checkin as pub

    await base.build_schema()
    try:
        ddl = importlib.import_module("app.services.net_session_link_ddl")
        async with base.engine.begin() as conn:
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
    except ImportError:
        pass
    ids = await base.seed()
    ORG_TOKEN = "tok-applecross-verify"
    jack, brad, graeme = ids["players"]

    tok_a = tok_b = sid_a = sid_b = cookie = None

    async def guarded(label, fn):
        """A step that cannot run (the control lacks what it needs) is a failed
        check, and the next step still runs."""
        try:
            await fn()
        except Exception as ex:  # noqa: BLE001
            base.FAIL += 1
            print(f"  FAIL {label}: step could not run ({type(ex).__name__}: {str(ex)[:90]})")

    async def as_admin(fn, *a, **kw):
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            user = await db.get(User, ids["user"])
            try:
                return await fn(*a, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e

    # Squads: Seniors = Jack + Brad, Colts = Graeme. Another club's team, too.
    seniors, colts, foreign_team = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    async with Session() as db:
        db.add(Team(id=seniors, organisation_id=ids["club"], name="Seniors", short_name="Srs", sequence=1))
        db.add(Team(id=colts, organisation_id=ids["club"], name="Colts", sequence=2))
        db.add(Team(id=foreign_team, organisation_id=ids["other"], name="Their 1st XI", sequence=1))
        await db.flush()
        for t, p in ((seniors, jack), (seniors, brad), (colts, graeme)):
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": t, "p": p, "o": ids["club"]})
        await db.commit()

    print("\n── Every new session has its own link ──")
    async def step_1():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        a, e = await as_admin(nm.create_session, nm.SessionCreate(label="Tuesday seniors", squad_team_ids=[str(seniors)]))
        b, e2 = await as_admin(nm.create_session, nm.SessionCreate(label="Tuesday open"))
        pa, pb = (a or {}).get("checkin_path"), (b or {}).get("checkin_path")
        check("a new session comes back with its own check-in path", bool(pa and pa.startswith("/nets-checkin/")), True)
        check("two sessions never share a token", bool(pa and pb and pa != pb))
        check("the session says which squads it is for", (a or {}).get("squad_team_ids"), [str(seniors)])
        check("an unrestricted session says everyone (empty)", (b or {}).get("squad_team_ids"), [])
        tok_a = (pa or "").rsplit("/", 1)[-1]
        tok_b = (pb or "").rsplit("/", 1)[-1]
        sid_a, sid_b = (a or {}).get("id"), (b or {}).get("id")
    await guarded("Every new session has its own link", step_1)

    print("\n── A session's link joins that session only ──")
    async def step_3():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        async with Session() as db:
            land = await pub.get_landing(tok_a, base.FakeRequest(), db) if tok_a else {}
        check("the session link lists exactly its session", [s["id"] for s in land.get("sessions", [])], [sid_a])
        check("...and says it is a scoped link", land.get("scoped"), True)
        names_a = {p["id"] for p in land.get("players", [])}
        check("...limited to the squad's members (Jack and Brad), so Graeme (Colts) is not on it",
              names_a, {str(jack), str(brad)})
        check("...and it names the squad", land.get("squads"), ["Srs"])
        async with Session() as db:
            land_org = await pub.get_landing(ORG_TOKEN, base.FakeRequest(), db)
        org_sessions = {s["id"] for s in land_org.get("sessions", [])}
        check("the club-wide link still lists every live session", {sid_a, sid_b} <= org_sessions, True)
        check("...and, with an open session in play, the whole list",
              {str(jack), str(brad), str(graeme)} <= {p["id"] for p in land_org.get("players", [])})
    await guarded("A session's link joins that session only", step_3)

    print("\n── Checking in through each link ──")
    async def step_5():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        async def verified_cookie(token, pid, pin):
            resp = base.FakeResponse()
            async with Session() as db:
                await pub.verify(token, pub.VerifyBody(player_id=str(pid), pin=pin), base.FakeRequest(), resp, db)
            return {pub.COOKIE_NAME: resp.cookies[pub.COOKIE_NAME]}

        async def rows_in(session_id):
            async with Session() as db:
                return (await db.execute(text("SELECT count(*) FROM net_attendance WHERE session_id = :s"), {"s": session_id})).scalar()

        cookie = await verified_cookie(tok_a, jack, "1234")
        async with Session() as db:
            r = await pub.check_in(tok_a, base.FakeRequest(cookies=cookie), db)
        check("the session link checks Jack into that session", [s["id"] for s in r["sessions"]], [sid_a])
        check("...and the other session is untouched", (await rows_in(sid_a), await rows_in(sid_b)), (1, 0))
        cookie_b = await verified_cookie(ORG_TOKEN, brad, "5678")
        async with Session() as db:
            r = await pub.check_in(ORG_TOKEN, base.FakeRequest(cookies=cookie_b), db)
        check("the club-wide link still checks into every live session",
              {s["id"] for s in r["sessions"]} >= {sid_a, sid_b}, True)
    await guarded("Checking in through each link", step_5)

    print("\n── Squads: PATCH rules ──")
    async def step_7():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        r, e = await as_admin(nm.update_session, sid_a, nm.SessionUpdate(label="Tuesday seniors (renamed)"))
        check("leaving squad_team_ids out leaves the squads alone", (r or {}).get("squad_team_ids"), [str(seniors)])
        r, e = await as_admin(nm.update_session, sid_a, nm.SessionUpdate(squad_team_ids=[str(foreign_team), str(colts)]))
        check("another club's team is never stored", (r or {}).get("squad_team_ids"), [str(colts)])
        r, e = await as_admin(nm.update_session, sid_a, nm.SessionUpdate(squad_team_ids=[]))
        check("an explicit empty list means everyone", (r or {}).get("squad_team_ids"), [])
        r, e = await as_admin(nm.update_session, sid_a, nm.SessionUpdate(squad_team_ids=[str(colts)]))
        async with Session() as db:
            land = await pub.get_landing(tok_a, base.FakeRequest(), db)
        check("changing the squad changes the list on its link", [p["id"] for p in land.get("players", [])], [str(graeme)])
    await guarded("Squads: PATCH rules", step_7)

    print("\n── Ended and regenerated links ──")
    async def step_9():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        r, e = await as_admin(nm.regenerate_session_checkin_link, sid_b) if hasattr(nm, "regenerate_session_checkin_link") else (None, None)
        new_tok_b = ((r or {}).get("token"))
        check("regenerating gives a different token", bool(new_tok_b) and new_tok_b != tok_b)
        try:
            async with Session() as db:
                await pub.get_landing(tok_b, base.FakeRequest(), db)
            old_dead = False
        except HTTPException as ex:
            old_dead = ex.status_code == 404
        check("...the old link is a 404", old_dead)
        async with Session() as db:
            land = await pub.get_landing(tok_a, base.FakeRequest(), db)
        check("...and the other session's link still works", [s["id"] for s in land.get("sessions", [])], [sid_a])

        r, e = await as_admin(nm.update_session, sid_a, nm.SessionUpdate(status="done"))
        async with Session() as db:
            land = await pub.get_landing(tok_a, base.FakeRequest(), db)
        check("an ended session's link lists no sessions", land.get("sessions"), [])
        try:
            async with Session() as db:
                await pub.check_in(tok_a, base.FakeRequest(cookies=cookie), db)
            refused = None
        except HTTPException as ex:
            refused = ex.status_code
        check("...and checking in through it is refused (409)", refused, 409)
    await guarded("Ended and regenerated links", step_9)

    print("\n── A session made before this change ──")
    async def step_11():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        legacy = uuid.uuid4()
        async with Session() as db:
            await db.execute(text(
                "INSERT INTO net_sessions (id, organisation_id, session_date, label, status, version) "
                "VALUES (:i, :o, CURRENT_DATE, 'Old session', 'active', 0)"), {"i": legacy, "o": ids["club"]})
            await db.commit()
        r, e = await as_admin(nm.get_session_checkin_link, str(legacy)) if hasattr(nm, "get_session_checkin_link") else (None, None)
        check("asking for its link mints one", bool((r or {}).get("token")))
        r2, _ = await as_admin(nm.get_session_checkin_link, str(legacy)) if hasattr(nm, "get_session_checkin_link") else (None, None)
        check("...and it is the same one next time", (r2 or {}).get("token"), (r or {}).get("token"))
    await guarded("A session made before this change", step_11)

    print("\n── The roster carries squads ──")
    async def step_13():
        nonlocal tok_a, tok_b, sid_a, sid_b, cookie
        async with Session() as db:
            club = await db.get(Organisation, ids["club"])
            ro = await nm.net_roster(db=db, club=club)
        by = {c["id"]: c for c in ro["players"]}
        check("each player lists their squads", sorted((by.get(str(jack)) or {}).get("squad_team_ids", [])), [str(seniors)])
        check("the roster lists the club's squads (and not another club's)",
              sorted(s["id"] for s in ro.get("squads", [])), sorted([str(seniors), str(colts)]))
    await guarded("The roster carries squads", step_13)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
