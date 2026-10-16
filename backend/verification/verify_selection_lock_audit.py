"""Verification: locking a confirmed side, the audit trail, "fill from last week"
and junior hiding on the selection overview, against a real Postgres.

Reported (Gisborne): a side that is "Ready to review" could not be confirmed
and nothing called it locked; there was no record of who changed a team; the
"fill from last week" button put another team's XI (men's) on the women's side;
junior fixtures cluttered team selection.

Drives the SHIPPED route bodies, never a re-implementation:
  * Confirm with lock=true saves the XI AND locks it; lock=false (the default)
    leaves it open, exactly as before
  * a locked side refuses a second Confirm and a draft write with 409 `locked`
  * a call-up that would pull a player out of a LOCKED lower side is blocked
    instead of changing it behind its selector's back
  * unlock opens it again; lock refuses an empty side
  * every confirm / lock / unlock / call-up writes an audit row with who, and
    the players before and after (added / removed / captain / keeper)
  * previous-xi comes from the SAME team only: a team with no history gets
    nothing, never another team's XI
  * the overview leaves junior grades out unless asked, and says which sides
    are locked

CONTROL MODE: against the previous commit the new routes and keys do not exist;
they are read through `.get` / presence checks, so the control FAILS, not crashes.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_selection_lock_audit.py
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

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

import verify_selection_same_day as base
from app.models.db import Organisation, User, Player, Team, Grade, Season, Fixture

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check


def code_of(e):
    d = getattr(e, "detail", None)
    return d.get("code") if isinstance(d, dict) else None


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    async with engine.begin() as conn:
        for stmt in DRAFT_DDL:
            await conn.execute(text(stmt))
    try:
        ddl = importlib.import_module("app.services.selection_lock_ddl")
        async with engine.begin() as conn:
            for stmt in ddl.STATEMENTS:
                await conn.execute(text(stmt))
    except ImportError:
        pass
    import app.routers.selection as sel

    org, user_id, season = (uuid.uuid4() for _ in range(3))
    g1, g2, gw, gj = (uuid.uuid4() for _ in range(4))
    t1, t2, tw = (uuid.uuid4() for _ in range(3))
    F1, F2, FW_old, FW, FJ = (uuid.uuid4() for _ in range(5))
    P = [uuid.uuid4() for _ in range(6)]
    d0 = date.today() + timedelta(days=10)

    async with Session() as db:
        db.add(Organisation(id=org, name="Lock CC", slug=f"lock-{org.hex[:8]}"))
        db.add(User(id=user_id, username=f"u{user_id.hex[:8]}", email=f"{user_id.hex[:8]}@x.com",
                    password_hash="x", display_name="Sam Selector"))
        db.add(Season(id=season, organisation_id=org, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g1, season_id=season, name="1st Grade", categories=["senior"]))
        db.add(Grade(id=g2, season_id=season, name="2nd Grade", categories=["senior"]))
        db.add(Grade(id=gw, season_id=season, name="Womens B Grade", categories=["womens"]))
        db.add(Grade(id=gj, season_id=season, name="Under 14 Blue", categories=["junior"]))
        await db.flush()
        db.add(Team(id=t1, organisation_id=org, name="1st Grade", sequence=1, grade_id=g1))
        db.add(Team(id=t2, organisation_id=org, name="2nd Grade", sequence=2, grade_id=g2))
        db.add(Team(id=tw, organisation_id=org, name="Womens B", sequence=3, grade_id=gw))
        await db.flush()
        for i, pid in enumerate(P):
            db.add(Player(id=pid, organisation_id=org, name=f"Player {i}", gender="male", is_player=True, status="active"))
        await db.flush()

        def fx(fid, team, grade, days, label):
            db.add(Fixture(id=fid, organisation_id=org, grade_id=grade, team_id=team, source="manual",
                           played_on=d0 + timedelta(days=days), status="UPCOMING", label=label, round=label))
        fx(F1, t1, g1, 0, "1st")
        fx(F2, t2, g2, 0, "2nd")
        fx(FW_old, tw, gw, -7, "W old")       # a past women's round with no XI
        fx(FW, tw, gw, 0, "W")
        fx(FJ, None, gj, 0, "U14")
        # The men's side has history; the women's side has none.
        await db.commit()

    async def as_user(fn, *args, **kw):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            try:
                return await fn(*args, db=db, club=club, user=user, **kw), None
            except HTTPException as e:
                return None, e

    async def as_club(fn, *args, **kw):
        """Read routes that take the club but not a user."""
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await fn(*args, db=db, club=club, **kw), None
            except HTTPException as e:
                return None, e

    async def confirm(fid, pids, cap=None, lock=None):
        async with Session() as db:
            club = await db.get(Organisation, org)
            user = await db.get(User, user_id)
            kw = {} if lock is None else {"lock": lock}
            try:
                body = sel.LineupSet(players=[
                    sel.LineupSlot(player_id=str(p), batting_order=i + 1, is_captain=(p == cap))
                    for i, p in enumerate(pids)], **kw)
                return await sel.set_selection(str(fid), body, db, club, user), None
            except HTTPException as e:
                return None, e

    async def scalar(sql, **kw):
        async with Session() as db:
            return (await db.execute(text(sql), kw)).scalar()

    has_lock = hasattr(sel, "lock_selection")
    print("\n# A. Confirm, lock, and what a lock refuses")
    r, e = await confirm(F1, [P[0], P[1], P[2]], cap=P[0])
    check("a plain confirm still works and does not lock", (r or {}).get("status"), "ok")
    check("...and leaves the side unlocked", await scalar("SELECT locked_at IS NULL FROM fixtures WHERE id=:f", f=F1), True)
    r, e = await confirm(F1, [P[0], P[1], P[3]], cap=P[0], lock=True)
    check("confirm with lock=true saves", (r or {}).get("status"), "ok")
    check("...and locks the side", await scalar("SELECT locked_at IS NOT NULL FROM fixtures WHERE id=:f", f=F1), True)
    check("...recording who locked it", await scalar("SELECT locked_by = CAST(:u AS uuid) FROM fixtures WHERE id=:f", f=F1, u=str(user_id)), True)
    r, e = await confirm(F1, [P[0], P[1]], cap=P[0])
    check("a second confirm on the locked side is refused 409 `locked`", (getattr(e, "status_code", None), code_of(e)), (409, "locked"))
    check("...and the XI is unchanged", await scalar("SELECT count(*) FROM fixture_lineups WHERE fixture_id=:f", f=F1), 3)
    r, e = await as_user(sel.save_draft, str(F1), sel.DraftSet(slots=[str(P[4])]))
    check("a draft write on the locked side is refused 409 `locked`", (getattr(e, "status_code", None), code_of(e)), (409, "locked"))

    print("\n# B. A call-up cannot reach into a LOCKED lower side")
    r, e = await confirm(F2, [P[4], P[5]], lock=True)         # 2nd XI confirmed + locked
    check("2nd XI confirmed and locked", (r or {}).get("locked"), True)
    # Unlock the 1st XI so we can pick someone already in the (locked) 2nd XI.
    r, e = await as_user(sel.unlock_selection, str(F1)) if has_lock else (None, None)
    check("unlock opens the 1st XI", (r or {}).get("locked"), False)
    r, e = await confirm(F1, [P[0], P[1], P[4]])              # P4 is in the locked 2nd XI
    check("calling up a player out of a locked 2nd XI is blocked (409)", getattr(e, "status_code", None), 409)
    check("...and the 2nd XI is untouched", await scalar("SELECT count(*) FROM fixture_lineups WHERE fixture_id=:f", f=F2), 2)
    r, e = await as_user(sel.unlock_selection, str(F2)) if has_lock else (None, None)
    r, e = await confirm(F1, [P[0], P[1], P[4]])
    check("once the 2nd XI is unlocked the same call-up goes through", (r or {}).get("status"), "ok")
    check("...and the player left the 2nd XI", await scalar("SELECT count(*) FROM fixture_lineups WHERE fixture_id=:f", f=F2), 1)

    print("\n# C. Lock and unlock directly")
    r, e = await as_user(sel.lock_selection, str(FW)) if has_lock else (None, None)
    check("locking a side with nobody named is refused (400)", getattr(e, "status_code", None), 400)
    r, e = await as_user(sel.lock_selection, str(F1)) if has_lock else (None, None)
    check("lock on a named side works", (r or {}).get("locked"), True)
    r, e = await as_user(sel.lock_selection, str(F1)) if has_lock else (None, None)
    check("locking twice is harmless", (r or {}).get("locked"), True)
    r, e = await as_user(sel.unlock_selection, str(F1)) if has_lock else (None, None)
    check("unlock works", (r or {}).get("locked"), False)

    print("\n# D. The audit trail")
    hist, _ = await as_club(sel.selection_history, str(F1)) if hasattr(sel, "selection_history") else ({"events": []}, None)
    ev = (hist or {}).get("events", [])
    actions = [x["action"] for x in ev]
    check("history lists confirmed, locked and unlocked for the 1st XI",
          {"confirmed", "locked", "unlocked"} <= set(actions), True)
    check("newest first (the last thing done is first)", actions[:1], ["unlocked"])
    check("every row says who", all(x.get("by") == "Sam Selector" for x in ev) and bool(ev), True)
    conf = [x for x in ev if x["action"] == "confirmed"]
    last = conf[0] if conf else {"detail": {}}
    check("the latest confirm records who came in", last["detail"].get("added"), ["Player 4"])
    check("...and who went out", sorted(last["detail"].get("removed", [])), ["Player 3"])
    first_conf = conf[-1]["detail"] if conf else {}
    check("the first confirm lists all three as added", sorted(first_conf.get("added", [])), ["Player 0", "Player 1", "Player 2"])
    check("the first confirm names the captain", first_conf.get("captain"), "Player 0")
    check("each confirm carries the full side before and after for a restore",
          bool(last["detail"].get("before")) and bool(last["detail"].get("after")), True)
    h2, _ = await as_club(sel.selection_history, str(F2)) if hasattr(sel, "selection_history") else ({"events": []}, None)
    check("the 2nd XI's history shows it was called up out of", "called_up_out" in [x["action"] for x in (h2 or {}).get("events", [])], True)

    print("\n# E. Fill from last week is the SAME team only")
    r, _ = await as_club(sel.previous_xi, str(FW))
    check("a women's side with no XI of its own gets nothing, not the men's", (r or {}).get("player_ids"), [])
    check("...and no source fixture", (r or {}).get("source_fixture_id"), None)
    # Give the women's side one old XI; now it should come back.
    async with Session() as db:
        await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id, batting_order) VALUES (:f,:p,:o,1)"),
                         {"f": FW_old, "p": P[5], "o": org})
        await db.commit()
    r, _ = await as_club(sel.previous_xi, str(FW))
    check("once the women's side has its own history it is used", (r or {}).get("player_ids"), [str(P[5])])
    r, _ = await as_club(sel.previous_xi, str(F2))
    check("the men's 2nd XI reads the 2nd XI's own last side, not the 1st XI's",
          all(p not in (r or {}).get("player_ids", []) for p in [str(P[0]), str(P[1])]), True)

    print("\n# F. The overview leaves juniors out and reports locks")
    r, _ = await as_club(sel.selection_overview)
    check("by default the overview is unchanged: the junior fixture is there",
          str(FJ) in {f["id"] for f in (r or {}).get("fixtures", [])}, True)
    r, _ = await as_club(sel.selection_overview, hide_juniors=True)
    ids = {f["id"] for f in (r or {}).get("fixtures", [])}
    check("hide_juniors leaves the junior fixture off", str(FJ) in ids, False)
    check("...and every senior and women's fixture stays", {str(F1), str(F2), str(FW)} <= ids, True)
    await as_user(sel.lock_selection, str(F1)) if has_lock else None
    r, _ = await as_club(sel.selection_overview)
    one = next((f for f in (r or {}).get("fixtures", []) if f["id"] == str(F1)), {})
    check("a locked side says locked on the overview", one.get("locked"), True)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
