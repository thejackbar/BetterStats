"""Verification: a dormant player can be marked "no longer dormant" (migration 348).

Reported (Gisborne, Oct 2026): a long-absent player coming back could not be put
in front of selectors until their first game back, because they read as dormant
and every BetterSelect screen hid them.

Through the SHIPPED route bodies and services, against a real Postgres:
  * the matrix: dormant, cleared, lapsed-clear and never-played players
  * the cleared player keeps their real `last_played`
  * `dormant_player_ids` / the self-service name list / the selection pool agree
  * `PUT /availability/players/{id}/dormancy` sets, undoes, audits, and is club-scoped
  * a clear lapses by itself once the dormancy window has passed from that day

CONTROL MODE: run against the commit before this change; keys are read through
`.get` and the endpoint through `getattr`, so the control reports failed checks
rather than crashing.

Run:  DATABASE_URL=postgresql+asyncpg://... python verification/verify_player_dormancy_cleared.py
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
from app.models.db import Organisation, Player, Team, Grade, Season, Fixture, Game, GameAppearance

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
check = base.check
TODAY = date.today()


def ago(days):
    return TODAY - timedelta(days=days)


async def main():
    await base.build_schema()
    from app.services.selection_draft_ddl import STATEMENTS as DRAFT_DDL
    from app.services.audit_ddl import STATEMENTS as AUDIT_DDL
    async with engine.begin() as conn:
        for stmt in list(DRAFT_DDL) + list(AUDIT_DDL):
            await conn.execute(text(stmt))
    from app.routers import availability as av
    from app.services.selection_pool import assemble_selection

    org_id, other_id, season_id, grade_id, team_id = (uuid.uuid4() for _ in range(5))
    async with Session() as db:
        db.add(Organisation(id=org_id, name="Dorm CC", slug=f"dorm-{org_id.hex[:8]}"))
        db.add(Organisation(id=other_id, name="Other CC", slug=f"oth-{other_id.hex[:8]}"))
        await db.flush()
        db.add(Season(id=season_id, organisation_id=org_id, name="2026/27", year=2026))
        await db.flush()
        db.add(Grade(id=grade_id, season_id=season_id, name="Saturday 1sts", categories=["senior"]))
        await db.flush()
        db.add(Team(id=team_id, organisation_id=org_id, name="1st XI", sequence=1, grade_id=grade_id))
        db.add(Fixture(id=uuid.uuid4(), organisation_id=org_id, grade_id=grade_id, team_id=team_id,
                       source="manual", played_on=TODAY + timedelta(days=5), start_time="13:00",
                       status="UPCOMING", label="1st XI"))
        await db.commit()

    ids: dict[str, uuid.UUID] = {}

    async def player(name, last_days_ago, cleared_days_ago=None, org=org_id):
        pid = uuid.uuid4()
        ids[name] = pid
        async with Session() as db:
            p = Player(id=pid, organisation_id=org, name=name, is_player=True, status="active",
                       dormancy_cleared_on=ago(cleared_days_ago) if cleared_days_ago is not None else None)
            db.add(p)
            await db.flush()
            if last_days_ago is not None:
                g = Game(id=uuid.uuid4(), grade_id=grade_id, played_at=ago(last_days_ago))
                db.add(g)
                await db.flush()
                db.add(GameAppearance(game_id=g.id, player_id=pid, team_name="1st XI"))
            await db.commit()
        return pid

    await player("Ann Current", 10)
    await player("Bob Dormant", 1100)                         # 3 years ago, nothing said
    await player("Cal Cleared", 1100, cleared_days_ago=0)     # 3 years ago, back today
    await player("Dee Lapsed", 1100, cleared_days_ago=800)    # cleared, but over the 24 month window ago
    await player("Eve New", None)                             # never played
    await player("Zed Other", 1100, org=other_id)

    async def matrix():
        async with Session() as db:
            club = await db.get(Organisation, org_id)
            body = await av.availability_matrix(db=db, club=club)
        return {p["display_name"]: p for p in body["players"]}

    m = await matrix()
    g = lambda n, k: (m.get(n) or {}).get(k)  # noqa: E731
    check("matrix: a dormant player is dormant", g("Bob Dormant", "is_dormant"), True)
    check("matrix: a player marked back is not dormant", g("Cal Cleared", "is_dormant"), False)
    check("matrix: ...and is current", g("Cal Cleared", "is_current"), True)
    check("matrix: ...but keeps their real last played date", g("Cal Cleared", "last_played"), ago(1100).isoformat())
    check("matrix: ...and carries the day they were marked", g("Cal Cleared", "dormancy_cleared_on"), TODAY.isoformat())
    check("matrix: a clear older than the window has lapsed (dormant again)", g("Dee Lapsed", "is_dormant"), True)
    check("matrix: a current player is untouched", g("Ann Current", "is_current"), True)
    check("matrix: a never-played player is not dormant (as before)", g("Eve New", "is_dormant"), False)
    check("matrix: nobody was marked, so the field is None", g("Bob Dormant", "dormancy_cleared_on"), None)

    async with Session() as db:
        club = await db.get(Organisation, org_id)
        dormant = await av.dormant_player_ids(db, club)
        names = {p.name for p in await av.active_self_service_players(db, club)}
    check("dormant_player_ids: Bob and Dee, not Cal", {ids["Bob Dormant"], ids["Dee Lapsed"]} == dormant, True)
    check("self-service list: Cal is on it, Bob is not", ("Cal Cleared" in names, "Bob Dormant" in names), (True, False))

    async with Session() as db:
        club = await db.get(Organisation, org_id)
        fx = (await db.execute(text("SELECT id FROM fixtures WHERE organisation_id = :o"), {"o": org_id})).scalar()
        sel = await assemble_selection(db, club, await db.get(Fixture, fx))
    pool = {r["display_name"]: r for r in sel["pool"]}
    check("selection pool: Cal is current, Bob is dormant",
          ((pool.get("Cal Cleared") or {}).get("is_current"), (pool.get("Bob Dormant") or {}).get("is_dormant")), (True, True))
    check("selection pool: Cal keeps the real last played date",
          (pool.get("Cal Cleared") or {}).get("last_played"), ago(1100).isoformat())

    # The Players list (Admin > Players) carries is_current for its Active filter.
    from app.routers import club_admin
    async with Session() as db:
        club = await db.get(Organisation, org_id)
        await db.execute(text("UPDATE players SET status = 'inactive' WHERE name = 'Eve New'"))
        await db.commit()
        rows = {r["name"]: r for r in await club_admin.list_players(current_user=None, club=club, db=db)}
    cur = lambda n: (rows.get(n) or {}).get("is_current")  # noqa: E731
    check("players list: a recent player is current", cur("Ann Current"), True)
    check("players list: a dormant player is not current", cur("Bob Dormant"), False)
    check("players list: a player marked back is current", cur("Cal Cleared"), True)
    check("players list: a lapsed clear is not current", cur("Dee Lapsed"), False)
    check("players list: a player marked inactive is not current, and not 'dormant'",
          (cur("Eve New"), (rows.get("Eve New") or {}).get("is_dormant")), (False, False))
    async with Session() as db:
        await db.execute(text("UPDATE players SET status = 'active' WHERE name = 'Eve New'"))
        await db.commit()

    # The endpoint.
    setter = getattr(av, "set_dormancy", None)
    Body = getattr(av, "DormancyBody", None)

    async def call(pid, active, org=org_id):
        async with Session() as db:
            club = await db.get(Organisation, org)
            try:
                return await setter(player_id=str(pid), body=Body(active=active), db=db, club=club, user=None)
            except Exception as e:  # noqa: BLE001 - HTTPException carries the status
                return {"error": getattr(e, "status_code", repr(e))}

    if setter and Body:
        r = await call(ids["Bob Dormant"], True)
        check("endpoint: marking Bob back stamps today", r.get("dormancy_cleared_on"), TODAY.isoformat())
        m = await matrix()
        check("endpoint: Bob now reads current in the matrix", (m["Bob Dormant"]["is_current"], m["Bob Dormant"]["is_dormant"]), (True, False))
        async with Session() as db:
            rows = (await db.execute(text(
                "SELECT area, action, player_name FROM audit_events WHERE organisation_id = :o"), {"o": org_id})).fetchall()
        check("endpoint: the change is in the audit trail", ("availability", "dormancy_cleared", "Bob Dormant") in [tuple(x) for x in rows], True)
        r = await call(ids["Bob Dormant"], False)
        check("endpoint: undoing clears the day", r.get("dormancy_cleared_on"), None)
        m = await matrix()
        check("endpoint: Bob is dormant again after the undo", m["Bob Dormant"]["is_dormant"], True)
        async with Session() as db:
            acts = [x[0] for x in (await db.execute(text(
                "SELECT action FROM audit_events WHERE organisation_id = :o"), {"o": org_id})).fetchall()]
        check("endpoint: the undo is audited too", "dormancy_restored" in acts, True)
        check("endpoint: another club's player is a 404", (await call(ids["Zed Other"], True)).get("error"), 404)
        check("endpoint: a bad id is a 404", (await call("not-a-uuid", True)).get("error"), 404)
    else:
        for label in ("marking back stamps today", "reads current", "audited", "undo clears", "dormant again",
                      "undo audited", "other club is 404", "bad id is 404"):
            check(f"endpoint: {label}", "no endpoint on this commit", "present")

    print(f"\n{base.PASS} passed, {base.FAIL} failed")
    await engine.dispose()
    sys.exit(1 if base.FAIL else 0)


asyncio.run(main())
