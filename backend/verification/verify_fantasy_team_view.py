"""Viewing another manager's locked team, and a ladder that follows a round being played, against Postgres.

Asked (Applecross): the overall ladder should update with live scores, and once a round is locked a manager
should be able to open the confirmed team of others in the league. Never the transfers they make ahead of the
next round: only the most recently locked team.

Drives the SHIPPED `routers/public_fantasy` route bodies (`team_view`, `ladder`) and `_league_standings` over
a real database. Only the club lookup and the session cookie read are stubbed.

What must NOT show is the point of most checks: a queued transfer, and a change applied after a round settled
(queued transfers are carried out then), must not reach another manager. Each is paired with a check that the
thing it hides is really there (the queued transfer exists; the squad's picks did change).

CONTROL: the ladder checks are the "before" (the previous `_league_standings` gave the last scored round as GW and
took it off a total that already held the running points); `team_view` did not exist, so the control reports the
route as missing.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_team_view.py
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason, FantasySquad,
    FantasySquadPlayer, Organisation, Player,
)
from app.routers import public_fantasy

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
PASS = FAIL = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


NOW = datetime.now(timezone.utc)
TODAY = date.today()
ORG, ORG2 = uuid.uuid4(), uuid.uuid4()
P1, P2, P3, P4 = (uuid.uuid4() for _ in range(4))
NAMES = {P1: "Alice Opener", P2: "Bob Spinner", P3: "Cara Keeper", P4: "Dan Quick"}
FS_ID, FS2 = uuid.uuid4(), uuid.uuid4()
R1, R2, R3 = (uuid.uuid4() for _ in range(3))
MGR = {k: uuid.uuid4() for k in "ABCXD"}
SQ = {k: uuid.uuid4() for k in "ABCX"}
LEAGUE = uuid.uuid4()
VIEWER = {"id": None}                                   # whose session cookie the stub returns


def lineup(pids, pts, captain=None):
    return [{"player_id": str(p), "role": "batter", "points": pts[i], "eff_points": pts[i] * (2 if p == captain else 1),
             "is_captain": p == captain, "is_vice": False, "captained": p == captain, "counted": True}
            for i, p in enumerate(pids)]


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS pgcrypto"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        await conn.execute(text("ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for stmt in COMP_STATEMENTS:
            await conn.execute(text(stmt))
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        for ddl in (
            """CREATE TABLE IF NOT EXISTS season_aliases (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE, undone_at TIMESTAMPTZ)""",
            """CREATE TABLE IF NOT EXISTS merge_logs (id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID,
                keep_player_id UUID, keep_player_name TEXT, removed_player_id UUID, removed_player_name TEXT, undone_at TIMESTAMPTZ)""",
        ):
            await conn.execute(text(ddl))
        for tbl, col in (await conn.execute(text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND data_type = 'json'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        s.add_all([Organisation(id=ORG, name="Applecross", slug="apx", is_active=True),
                   Organisation(id=ORG2, name="Other CC", slug="other", is_active=True)])
        await s.flush()
        for pid, nm in NAMES.items():
            s.add(Player(id=pid, name=nm, organisation_id=ORG, grassroots_id=str(pid)))
        s.add_all([
            FantasySeason(id=FS_ID, organisation_id=ORG, season_year=TODAY.year, name="Fantasy", status="active", scoring={}, rules={}),
            FantasySeason(id=FS2, organisation_id=ORG2, season_year=TODAY.year, name="Other", status="active", scoring={}, rules={}),
        ])
        await s.flush()
        day = lambda n: TODAY + timedelta(days=n)  # noqa: E731
        s.add_all([
            FantasyRound(id=R1, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=1, name="Round 1", status="scored",
                         start_date=day(-20), end_date=day(-19), lock_at=NOW - timedelta(days=20)),
            FantasyRound(id=R2, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=2, name="Round 2", status="upcoming",
                         start_date=day(-1), end_date=day(6), lock_at=NOW - timedelta(days=1)),
            FantasyRound(id=R3, fantasy_season_id=FS_ID, organisation_id=ORG, round_number=3, name="Round 3", status="upcoming",
                         start_date=day(13), end_date=day(14), lock_at=NOW + timedelta(days=13)),
        ])
        s.add(FantasyLeague(id=LEAGUE, fantasy_season_id=FS_ID, organisation_id=ORG, kind="global_salary_cap", name="Club ladder"))
        for k in "ABCXD":
            s.add(FantasyManager(id=MGR[k], organisation_id=ORG if k != "X" else ORG2, display_name=f"Manager {k}"))
        await s.flush()
        for k, jr in (("A", None), ("B", None), ("C", 3)):
            s.add(FantasySquad(id=SQ[k], fantasy_season_id=FS_ID, league_id=LEAGUE, manager_id=MGR[k], organisation_id=ORG,
                               team_name=f"Team {k}", free_transfers=1, joined_round=jr))
        await s.flush()
        s.add_all([FantasySquadPlayer(squad_id=SQ["A"], player_id=P3, role="batter", is_captain=True),
                   FantasySquadPlayer(squad_id=SQ["A"], player_id=P4, role="batter"),
                   FantasySquadPlayer(squad_id=SQ["B"], player_id=P1, role="batter", is_captain=True),
                   FantasySquadPlayer(squad_id=SQ["B"], player_id=P2, role="batter"),
                   FantasySquadPlayer(squad_id=SQ["C"], player_id=P4, role="batter", is_captain=True)])
        await s.commit()
    async with Session() as s:
        async def srs(k, rid, points, lu, chip=None):
            await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup, chip_used) "
                                 "VALUES (:s, :r, :p, :p, CAST(:l AS JSONB), :c)"),
                            {"s": SQ[k], "r": rid, "p": points, "l": json.dumps(lu), "c": chip})
        # Round 1 (scored): B 20, A 5.
        await srs("A", R1, 5, lineup([P3, P4], [3, 2], P3))
        await srs("B", R1, 20, lineup([P1, P2], [12, 8], P1))
        # Round 2 (locked, being played): A 30 (a wildcard played), B 10: running points.
        await srs("A", R2, 30, lineup([P3, P4], [18, 12], P3), chip="wildcard")
        await srs("B", R2, 10, lineup([P1, P2], [6, 4], P1))
        await s.execute(text("UPDATE fantasy_squads SET total_points = 35 WHERE id=:i"), {"i": SQ["A"]})
        await s.execute(text("UPDATE fantasy_squads SET total_points = 30 WHERE id=:i"), {"i": SQ["B"]})
        await s.commit()


async def call(fn, **kw):
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        public_fantasy._club_for_token = lambda db, token: _async(org)
        public_fantasy._read_session = lambda request, club_id: VIEWER["id"]
        return await fn(db=s, **kw)


async def _async(v):
    return v


async def set_picks(k, pids):
    async with Session() as s:
        await s.execute(text("DELETE FROM fantasy_squad_players WHERE squad_id=:s"), {"s": SQ[k]})
        for i, p in enumerate(pids):
            await s.execute(text("INSERT INTO fantasy_squad_players (squad_id, player_id, role, is_captain, is_vice_captain) "
                                 "VALUES (:s, :p, 'batter', :c, false)"), {"s": SQ[k], "p": p, "c": i == 0})
        await s.commit()


async def team(target, viewer="A"):
    VIEWER["id"] = MGR[viewer]
    return await call(public_fantasy.team_view, token="t", squad_id=str(SQ[target]) if target in SQ else target,
                      request=SimpleNamespace())


async def status_of(target, viewer="A"):
    try:
        await team(target, viewer)
        return 200
    except HTTPException as e:
        return e.status_code


async def ladder(viewer="A"):
    VIEWER["id"] = MGR[viewer]
    return await call(public_fantasy.ladder, token="t", request=SimpleNamespace())


def pids_of(view):
    return [e["player_id"] for e in (view.get("lineup") or [])]


async def main() -> None:
    await build_schema()
    await seed()
    has_route = hasattr(public_fantasy, "team_view")

    print("\n-- 1. The ladder follows the round being played --")
    L = await ladder()
    rows = {r["team_name"]: r for r in L["ladder"]}
    check("the GW column is the running round's points (A 30, B 10), not round 1's (5 and 20)",
          rows["Team A"]["gw"] == 30 and rows["Team B"]["gw"] == 10, f"{rows['Team A']['gw']} {rows['Team B']['gw']}")
    check("A (35) is ahead of B (30) on the live total", rows["Team A"]["rank"] == 1 and rows["Team B"]["rank"] == 2)
    check("and the arrows compare with the table BEFORE this round: A climbed one place, B fell one",
          rows["Team A"]["rank_delta"] == 1 and rows["Team B"]["rank_delta"] == -1,
          f"A {rows['Team A']['rank_delta']} B {rows['Team B']['rank_delta']}")
    check("the response says a round is live", (L.get("live") or {}).get("number") == 2, str(L.get("live")))

    print("\n-- 2. Teams can be opened only once a round has locked --")
    check("the ladder says teams can be opened", L.get("teams_visible") is True, str(L.get("teams_visible")))
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() + INTERVAL '1 day' WHERE id IN (:a,:b)"), {"a": R1, "b": R2})
        await s.commit()
    check("before any round has locked it is refused (403)", await status_of("B") == 403 if has_route else False)
    check("and the ladder says teams cannot be opened yet", (await ladder()).get("teams_visible") is False)
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() - INTERVAL '20 days' WHERE id=:a"), {"a": R1})
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() - INTERVAL '1 day' WHERE id=:a"), {"a": R2})
        await s.commit()

    print("\n-- 3. Round 2 is locked and being played: B's locked team --")
    if not has_route:
        check("the team view route exists", False, "team_view missing")
        print(f"\n{PASS} passed, {FAIL} failed")
        await engine.dispose()
        sys.exit(1 if FAIL else 0)
    v = await team("B")
    check("it is round 2, live, B's own XI as locked", v["round"] == {"number": 2, "name": "Round 2", "status": "live"}
          and set(pids_of(v)) == {str(P1), str(P2)} and v["team_name"] == "Team B" and v["manager"] == "Manager B", str(v))
    check("with the running points (10) and names", v["points"] == 10 and {e["name"] for e in v["lineup"]} == {"Alice Opener", "Bob Spinner"})
    va = await team("A", viewer="B")
    check("a chip played for the locked round shows (A's wildcard)", va["chip_used"] == "wildcard")
    check("you can open your own team, flagged", (await team("A", viewer="A"))["you"] is True)
    allowed = {"squad_id", "team_name", "manager", "you", "total_points", "round", "lineup", "points", "chip_used"}
    check("only those fields: no prices, bank, free transfers or queued transfers", set(v) <= allowed, str(sorted(set(v) - allowed)))
    check("nor in any lineup entry", all(set(e) <= {"player_id", "role", "points", "eff_points", "is_captain", "is_vice", "captained",
                                                    "counted", "name", "photo_url", "initials"} for e in v["lineup"]),
          str(v["lineup"][0]))

    print("\n-- 4. A transfer B queues after the lock is not shown --")
    async with Session() as s:
        await s.execute(text("INSERT INTO fantasy_queued_transfers (fantasy_season_id, squad_id, after_round_id, out_player_id, in_player_id) "
                             "VALUES (:fs, :s, :r, :o, :i)"), {"fs": FS_ID, "s": SQ["B"], "r": R2, "o": P2, "i": P3})
        await s.commit()
    async with Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM fantasy_queued_transfers WHERE squad_id=:s"), {"s": SQ["B"]})).scalar()
    check("(B really has a transfer queued)", n == 1, str(n))
    v = await team("B")
    blob = json.dumps(v)
    check("B's locked team is unchanged", set(pids_of(v)) == {str(P1), str(P2)})
    check("and nothing about the incoming player appears anywhere in the response", str(P3) not in blob and "Cara Keeper" not in blob)

    print("\n-- 5. Round 2 settles, the queued transfer is carried out, round 3 has NOT locked --")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET status='scored', scored_at=NOW() WHERE id=:a"), {"a": R2})
        await s.commit()
    await set_picks("B", [P1, P3])                    # what apply_pending does after settlement
    async with Session() as s:
        now_picks = {str(r[0]) for r in (await s.execute(text("SELECT player_id FROM fantasy_squad_players WHERE squad_id=:s"), {"s": SQ["B"]})).all()}
    check("(B's picks really did change: Bob out, Cara in)", now_picks == {str(P1), str(P3)}, str(now_picks))
    v = await team("B")
    check("round 2 is still the most recently LOCKED round, now scored", v["round"]["number"] == 2 and v["round"]["status"] == "scored", str(v["round"]))
    check("B's team is still the one locked for round 2 (Bob), not the one for round 3 (Cara)",
          set(pids_of(v)) == {str(P1), str(P2)} and str(P3) not in json.dumps(v), str(pids_of(v)))

    print("\n-- 6. Round 3 locks: the team is then the one locked for round 3 --")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET lock_at = NOW() - INTERVAL '1 hour' WHERE id=:a"), {"a": R3})
        await s.commit()
    v = await team("B")
    check("round 3, live, with the picks now frozen (Alice and Cara)", v["round"]["number"] == 3 and v["round"]["status"] == "live"
          and set(pids_of(v)) == {str(P1), str(P3)}, str(v))
    check("with no points yet", v["points"] == 0)

    print("\n-- 7. Who can look, and at what --")
    c3 = await team("C", viewer="A")
    check("a team that joined FOR the locked round (round 3) does show its team", c3["lineup"] is not None and c3["round"]["number"] == 3)
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_squads SET joined_round = 4 WHERE id=:i"), {"i": SQ["C"]})
        await s.commit()
    c = await team("C", viewer="A")
    check("a team that joined after the round locked has nothing to show, and says so",
          c["lineup"] is None and "joined after" in (c.get("note") or ""), str(c))
    check("a manager of this club with no squad yet is refused (403)", await status_of("B", viewer="D") == 403)
    check("a manager from another club is refused (401)", await status_of("B", viewer="X") == 401)
    VIEWER["id"] = None
    try:
        await call(public_fantasy.team_view, token="t", squad_id=str(SQ["B"]), request=SimpleNamespace())
        anon = 200
    except HTTPException as e:
        anon = e.status_code
    check("someone not signed in is refused (401)", anon == 401, str(anon))
    check("a squad id that is not in the league is a 404", await status_of(str(uuid.uuid4())) == 404)
    check("so is one that is not an id", await status_of("not-an-id") == 404)

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    asyncio.run(main())
