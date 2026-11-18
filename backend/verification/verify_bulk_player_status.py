"""Marking many players inactive (or active) in one go. Real Postgres.

Reported by a new club (Piara Waters): ~500 past players had to be made inactive one at a time.
Drives the SHIPPED route body `routers/players.bulk_player_status`:

  * every picked player of the club goes inactive in one request, and leaves every squad, the same rule
    as one at a time (`update_player_profile`);
  * a player already inactive is counted unchanged, not written again;
  * another club's player id and junk ids are ignored and counted, never changed;
  * one audit row names exactly who changed;
  * marking active puts them back to active and into no squad;
  * a bad status is refused and changes nothing.

Control run: on the previous commit the route does not exist (read through getattr), so every check fails.

Run:  DATABASE_URL=postgresql+asyncpg://root@/bulkstatus?host=/var/run/postgresql \
      python verification/verify_bulk_player_status.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base, Organisation, Player, Team, User
from app.routers import players as players_router
from app.services import squad_membership as sm

engine = create_async_engine(os.environ["DATABASE_URL"], echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


OURS, OTHER, USER = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
T1, T2 = uuid.uuid4(), uuid.uuid4()
PAST = [uuid.uuid4() for _ in range(30)]
KEEP, ALREADY, THEIRS = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

bulk = getattr(players_router, "bulk_player_status", None)
BulkIn = getattr(players_router, "BulkStatusIn", None)


async def statuses() -> dict:
    async with Session() as s:
        return {r[0]: r[1] for r in (await s.execute(text("SELECT id, status FROM players"))).all()}


async def memberships(pid) -> int:
    async with Session() as s:
        return (await s.execute(text("SELECT count(*) FROM team_members WHERE player_id = :p"), {"p": pid})).scalar()


async def call(ids, status):
    if bulk is None:
        return None, "missing"
    async with Session() as s:
        user = await s.get(User, USER)
        try:
            return await bulk(body=BulkIn(player_ids=[str(i) for i in ids], status=status), db=s, user=user,
                              club=Organisation(id=OURS)), None
        except HTTPException as e:
            await s.rollback()
            return None, e


async def main() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        from app.services.audit_ddl import STATEMENTS as AUDIT
        from app.services.team_sides_ddl import STATEMENTS as SIDES
        for stmt in list(AUDIT) + list(SIDES):
            await conn.execute(text(stmt))
    async with Session() as s:
        s.add(Organisation(id=OURS, name="Piara Waters CC", slug="piara"))
        s.add(Organisation(id=OTHER, name="Rivals CC", slug="rivals"))
        s.add(User(id=USER, username="admin", display_name="Club Admin", email="a@x.com", password_hash="x"))
        s.add(Team(id=T1, organisation_id=OURS, name="1st XI", sequence=1))
        s.add(Team(id=T2, organisation_id=OURS, name="2nd XI", sequence=2))
        for i, pid in enumerate(PAST):
            s.add(Player(id=pid, organisation_id=OURS, name=f"Past Player {i}", status="active"))
        s.add(Player(id=KEEP, organisation_id=OURS, name="Current Player", status="active"))
        s.add(Player(id=ALREADY, organisation_id=OURS, name="Already Gone", status="inactive"))
        s.add(Player(id=THEIRS, organisation_id=OTHER, name="Their Player", status="active"))
        await s.commit()
        for pid in PAST[:5]:
            await sm.add_squad_memberships(s, OURS, pid, [T1, T2], USER)
        await sm.add_squad_memberships(s, OURS, KEEP, [T1], USER)
        await s.commit()

    print("1. Mark thirty past players inactive at once")
    check("before: five of them are in two squads each", all([await memberships(p) == 2 for p in PAST[:5]]))
    res, err = await call(PAST + [ALREADY, THEIRS, "not-an-id"], "inactive")
    check("one request saves", err is None and res is not None, str(err))
    st = await statuses()
    check("all thirty are inactive", all(st[p] == "inactive" for p in PAST), str([st[p] for p in PAST[:3]]))
    check("and out of every squad", all([await memberships(p) == 0 for p in PAST[:5]]))
    check("the counts: 30 updated, 1 already inactive, 2 not the club's",
          res == {"updated": 30, "unchanged": 1, "not_found": 2}, str(res))
    check("another club's player is untouched", st[THEIRS] == "active")
    check("a player not picked is untouched, squad and all", st[KEEP] == "active" and await memberships(KEEP) == 1)
    async with Session() as s:
        rows = (await s.execute(text(
            "SELECT summary, detail FROM audit_events WHERE action = 'bulk_status'"))).all() if bulk else []
    check("one audit row naming exactly the thirty who changed",
          len(rows) == 1 and sorted(rows[0][1]["player_ids"]) == sorted(map(str, PAST))
          and rows[0][0] == "30 players marked inactive", str(rows[:1])[:200])

    print("2. Mark some of them active again")
    res, err = await call(PAST[:2], "active")
    st = await statuses()
    check("they are active", err is None and st[PAST[0]] == "active" and st[PAST[1]] == "active", str(err))
    check("and in no squad (which squad is the club's call)", await memberships(PAST[0]) == 0)

    print("3. A bad status changes nothing")
    before = await statuses()
    res, err = await call(PAST, "retired")
    check("refused (400)", getattr(err, "status_code", None) == 400, str(err))
    check("nothing changed", await statuses() == before)

    print()
    print(f"{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
