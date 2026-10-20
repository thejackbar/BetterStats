"""Verification: the player's private page on the self-service availability link,
against a real Postgres.

Reported (Gisborne): players should see their squad when they log in to give
availability, and have a personal page with their availability, squad, selection
and training. Drives the SHIPPED route bodies (`get_me`, `get_my_profile`):

  * squads show only when the club has the show-squad switch on; with it off no
    squad (and no side name) appears anywhere in the response
  * a side shows only once it is LOCKED, only for the player named in it, only
    in the future, never when cancelled; nobody else's name is in the payload
  * captain / keeper are flagged on the player's own entry
  * training lists coming sessions that are for everyone or for the player's
    squad, and counts the player's own attendance over eight weeks
  * junior fixtures are left off a senior player's page and kept for a player in
    a junior squad (Manage Grades decides what is junior)
  * no cookie, no page (401)

CONTROL MODE: against the previous commit `get_my_profile` does not exist; it is
read through `getattr`, so the control FAILS checks rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_profile.py
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
from app.models.db import Fixture, Grade, Organisation, Season, Team

check = base.check
Session = base.Session


async def main():
    import app.routers.public_availability as pa

    await base.build_schema()
    # Lifespan-only tables the grade classification reads (copied from the
    # lifespan, as in the selection suites).
    async with base.engine.begin() as conn:
        for ddl_ in (
            """CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(ddl_))
    for modname in ("selection_lock_ddl", "net_session_link_ddl", "selection_draft_ddl"):
        try:
            ddl = importlib.import_module(f"app.services.{modname}")
            async with base.engine.begin() as conn:
                for stmt in ddl.STATEMENTS:
                    await conn.execute(text(stmt))
        except ImportError:
            pass
    ids = await base.seed()
    jack, brad, graeme = ids["players"]
    TOKEN = "avail-tok-verify"
    today = date.today()

    async with Session() as db:
        club = await db.get(Organisation, ids["club"])
        club.availability_link_token = TOKEN
        club.availability_self_service_enabled = True
        club.availability_require_pin = False
        club.availability_show_squad = False
        season, g_sen, g_jun = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add(Season(id=season, organisation_id=club.id, name="Summer", year=2026))
        await db.flush()
        db.add(Grade(id=g_sen, season_id=season, name="1st Grade", categories=["senior"]))
        db.add(Grade(id=g_jun, season_id=season, name="Under 14 Blue", categories=["junior"]))
        await db.flush()
        t_sen, t_jun, t_other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        db.add(Team(id=t_sen, organisation_id=club.id, name="1st XI", short_name="1sts", sequence=1, grade_id=g_sen))
        db.add(Team(id=t_jun, organisation_id=club.id, name="U14 Blue", sequence=9, grade_id=g_jun))
        db.add(Team(id=t_other, organisation_id=club.id, name="3rd XI", sequence=3))
        await db.flush()
        for t, p in ((t_sen, jack), (t_jun, graeme)):
            await db.execute(text("INSERT INTO team_members (team_id, player_id, organisation_id) VALUES (:t,:p,:o)"),
                             {"t": t, "p": p, "o": club.id})

        def fx(grade, team, days, label, **kw):
            f = Fixture(id=uuid.uuid4(), organisation_id=club.id, grade_id=grade, team_id=team, source="manual",
                        played_on=today + timedelta(days=days), start_time="13:00", status="UPCOMING",
                        opponent_name=label, **kw)
            db.add(f)
            return f
        f_locked = fx(g_sen, t_sen, 5, "Rovers", locked_at=datetime.now(timezone.utc))
        f_open = fx(g_sen, t_sen, 6, "Wanderers")
        f_cancel = fx(g_sen, t_sen, 7, "Saints", locked_at=datetime.now(timezone.utc))
        f_cancel.status = "CANCELLED"
        f_past = fx(g_sen, t_sen, -3, "Old", locked_at=datetime.now(timezone.utc))
        f_other = fx(g_sen, t_sen, 8, "Others", locked_at=datetime.now(timezone.utc))
        f_junior = fx(g_jun, t_jun, 9, "Kids")
        await db.flush()
        for f, pid, cap in ((f_locked, jack, True), (f_open, jack, False), (f_cancel, jack, False),
                            (f_past, jack, False), (f_other, brad, False), (f_junior, graeme, False)):
            await db.execute(text("INSERT INTO fixture_lineups (fixture_id, player_id, organisation_id, batting_order, is_captain) "
                                  "VALUES (:f,:p,:o,1,:c)"), {"f": f.id, "p": pid, "o": club.id, "c": cap})
        # Training: one for everyone, one for the 3rd XI only, one for the 1st XI only.
        def ns(days, label, squads):
            return (uuid.uuid4(), club.id, today + timedelta(days=days), label, squads)
        for sid, org, d, label, squads in (ns(2, "Open nets", None), ns(3, "Thirds only", [t_other]), ns(4, "Firsts only", [t_sen])):
            await db.execute(text("INSERT INTO net_sessions (id, organisation_id, session_date, label, status, version, squad_team_ids) "
                                  "VALUES (:i,:o,:d,:l,'active',0,CAST(:s AS uuid[]))"),
                             {"i": sid, "o": org, "d": d, "l": label, "s": squads})
        # Jack turned up to two sessions in the last eight weeks (and one long ago).
        for days_ago in (6, 20, 100):
            sid = uuid.uuid4()
            await db.execute(text("INSERT INTO net_sessions (id, organisation_id, session_date, label, status, version) VALUES (:i,:o,:d,'Past','done',0)"),
                             {"i": sid, "o": club.id, "d": today - timedelta(days=days_ago)})
            await db.execute(text("INSERT INTO net_attendance (id, session_id, organisation_id, player_id, batted) VALUES (:a,:s,:o,:p,false)"),
                             {"a": uuid.uuid4(), "s": sid, "o": club.id, "p": jack})
        await db.commit()

    def cookie_for(pid):
        resp = base.FakeResponse()
        pa._issue_cookie(resp, ids["club"], pid)
        return {pa.COOKIE_NAME: resp.cookies[pa.COOKIE_NAME]}

    async def profile(pid, **kw):
        async with Session() as db:
            req = base.FakeRequest(cookies=cookie_for(pid))
            fn = getattr(pa, "get_my_profile", None)
            if fn is None:
                return {}
            return await fn(TOKEN, req, db=db, **kw)

    async def me(pid):
        async with Session() as db:
            return await pa.get_me(TOKEN, base.FakeRequest(cookies=cookie_for(pid)), db=db)

    async def set_show_squad(on):
        async with Session() as db:
            await db.execute(text("UPDATE organisations SET availability_show_squad = :v WHERE id = :o"), {"v": on, "o": ids["club"]})
            await db.commit()

    print("\n── The squad switch ──")
    p = await profile(jack)
    check("with the switch off the page names no squad", (p.get("squads"), p.get("squads_visible")), ([], False))
    check("...nor the side's name on a selection", all(s.get("team_name") is None for s in p.get("selected", [])) and bool(p.get("selected")), True)
    m = await me(jack)
    check("...and the availability page carries none either", m.get("squads"), [])
    await set_show_squad(True)
    p = await profile(jack)
    check("switched on, the player sees their squad by name", p.get("squads"), ["1sts"])
    check("...and the availability page shows it too", (await me(jack)).get("squads"), ["1sts"])
    check("...and a selection names the side", [s.get("team_name") for s in p.get("selected", [])], ["1sts"])

    print("\n── Selection ──")
    sel = p.get("selected", [])
    check("only the locked, future, live side shows (not unlocked, past or cancelled)", [s["opponent_name"] for s in sel], ["Rovers"])
    check("the player is flagged captain on their own entry", (sel[0]["is_captain"], sel[0]["is_wicket_keeper"]) if sel else None, (True, False))
    check("another player's locked side does not appear", "Others" not in str(p))
    p2 = await profile(brad)
    check("a player in a locked side sees only their own", [s["opponent_name"] for s in p2.get("selected", [])], ["Others"])

    print("\n── Training ──")
    tr = p.get("training", {})
    check("coming sessions are those for everyone or the 1sts, not the 3rds' (tonight's seeded one included)", [s["label"] for s in tr.get("upcoming", [])], ["Tuesday senior nets", "Open nets", "Firsts only"])
    check("attendance counts the last eight weeks only (2, not 3)", tr.get("attended_8_weeks"), 2)
    check("...and says when they last turned up", tr.get("last_attended"), (today - timedelta(days=6)).isoformat())

    print("\n── Juniors on the availability page ──")
    senior_dates = await me(jack)
    check("a senior player's page leaves out junior games", "Kids" not in str(senior_dates.get("dates")), True)
    junior_dates = await me(graeme)
    check("a player in a junior squad keeps theirs", "Kids" in str(junior_dates.get("dates")), True)

    print("\n── Not signed in ──")
    try:
        async with Session() as db:
            fn = getattr(pa, "get_my_profile", None)
            await fn(TOKEN, base.FakeRequest(), db=db) if fn else (_ for _ in ()).throw(HTTPException(status_code=0, detail="absent"))
        code = None
    except HTTPException as e:
        code = e.status_code
    check("no cookie means no page (401)", code, 401)

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    return 1 if base.FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
