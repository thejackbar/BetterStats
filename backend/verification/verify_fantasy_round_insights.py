"""Round insights for the Fantasy public page, against Postgres.

Asked: more colour on the public page. A top 10 of players for each round, the players traded out and traded in
most, the biggest price risers and fallers, with a filter by round.

Drives the SHIPPED `public_fantasy.round_insights` route body and `services/fantasy_round_insights` over a real
database. Only the club lookup is stubbed.

Pinned here:
  * Top scorers: highest first, a player who did not play is left out, only the top 10, `picked_by` counts the
    teams that locked the player, and a name an admin set is the name shown.
  * Trades: counted for the round they were made for, only the top 10, only the club-wide league's teams, and a
    transfer taken back when a round was unsettled is not counted (paired with a check that its rows exist).
  * Price risers and fallers are the moves that round made (not another round's), biggest first.
  * Offered rounds are the scored ones plus the open round; the open round shows trades and no points or moves.
  * Derived on read: unsettling a round takes it out.

CONTROL: the route does not exist before this change, so against the previous commit every check reports the
route as missing instead of crashing.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_round_insights.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, FantasyLeague, FantasyManager, FantasyPoolPlayer, FantasyRound, FantasySeason, FantasySquad, Organisation, Player,
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
FS_ID, FS2 = uuid.uuid4(), uuid.uuid4()
RID = {n: uuid.uuid4() for n in range(1, 6)}
MGR = {k: uuid.uuid4() for k in "ABCX"}
SQ = {k: uuid.uuid4() for k in "ABCX"}
LEAGUE, LEAGUE2 = uuid.uuid4(), uuid.uuid4()
PL = {i: uuid.uuid4() for i in range(1, 14)}            # Player 01 .. Player 13
# Round 1 points per game. Equal starting prices, so each move is (points - 60) / 200 to the nearest 0.1.
R1_PTS = {1: 120, 2: 100, 3: 80, 4: 60, 5: 40, 6: 20, 7: 0, 8: 60, 9: 60, 10: 60, 11: 60, 12: 60}
STATUS = {1: "scored", 2: "scored", 3: "upcoming", 4: "upcoming", 5: "unsettled"}


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
        for i, pid in PL.items():
            s.add(Player(id=pid, name=f"Player {i:02d}", organisation_id=ORG, grassroots_id=str(pid),
                         display_name_override="Nick Name" if i == 2 else None))
        s.add_all([
            FantasySeason(id=FS_ID, organisation_id=ORG, season_year=TODAY.year, name="Fantasy", status="active", scoring={}, rules={}),
            FantasySeason(id=FS2, organisation_id=ORG2, season_year=TODAY.year, name="Other", status="active", scoring={}, rules={}),
        ])
        await s.flush()
        for n, st in STATUS.items():
            s.add(FantasyRound(id=RID[n], fantasy_season_id=FS_ID, organisation_id=ORG, round_number=n, name=f"Round {n}", status=st,
                               start_date=TODAY - timedelta(days=60 - n * 7), end_date=TODAY - timedelta(days=59 - n * 7),
                               lock_at=NOW + timedelta(days=n)))
        s.add_all([
            FantasyLeague(id=LEAGUE, fantasy_season_id=FS_ID, organisation_id=ORG, kind="global_salary_cap", name="Club ladder"),
            FantasyLeague(id=LEAGUE2, fantasy_season_id=FS2, organisation_id=ORG2, kind="global_salary_cap", name="Other ladder"),
        ])
        for k in "ABCX":
            s.add(FantasyManager(id=MGR[k], organisation_id=ORG if k != "X" else ORG2, display_name=f"Manager {k}"))
        await s.flush()
        for k in "ABC":
            s.add(FantasySquad(id=SQ[k], fantasy_season_id=FS_ID, league_id=LEAGUE, manager_id=MGR[k], organisation_id=ORG, team_name=f"Team {k}"))
        s.add(FantasySquad(id=SQ["X"], fantasy_season_id=FS2, league_id=LEAGUE2, manager_id=MGR["X"], organisation_id=ORG2, team_name="Team X"))
        for i, pid in PL.items():
            s.add(FantasyPoolPlayer(fantasy_season_id=FS_ID, organisation_id=ORG, player_id=pid, role="batter",
                                    base_price=8.0, current_price=8.0))
        await s.commit()
    async with Session() as s:
        async def prs(rn, i, pts, games=1):
            await s.execute(text("INSERT INTO fantasy_player_round_scores (fantasy_season_id, round_id, player_id, base_points, total_points, games_counted) "
                                 "VALUES (:fs, :r, :p, :t, :t, :g)"), {"fs": FS_ID, "r": RID[rn], "p": PL[i], "t": pts, "g": games})
        for i, pts in R1_PTS.items():
            await prs(1, i, pts)
        await prs(1, 13, 0, games=0)                       # on the sheet, did not play
        # Round 2: Player 07 has a huge day, everyone else is flat.
        for i in range(1, 13):
            await prs(2, i, 150 if i == 7 else 60)

        async def lineup(k, rn, ids):
            import json
            await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup) "
                                 "VALUES (:s, :r, 10, 10, CAST(:l AS JSONB))"),
                            {"s": SQ[k], "r": RID[rn], "l": json.dumps([{"player_id": str(PL[i]), "role": "batter", "points": 1} for i in ids])})
        await lineup("A", 1, [1, 2, 3]); await lineup("B", 1, [1, 4]); await lineup("C", 1, [5])    # Player 01 is in two teams

        async def tx(k, rn, typ, i, queued=None, ago=0):
            import json
            await s.execute(text("INSERT INTO fantasy_transactions (squad_id, league_id, round_id, type, player_id, price, detail, created_at) "
                                 "VALUES (:s, :lg, :r, :t, :p, 8.0, CAST(:d AS JSONB), :at)"),
                            {"s": SQ[k], "lg": LEAGUE2 if k == "X" else LEAGUE, "r": RID[rn], "t": typ, "p": PL[i],
                             "d": json.dumps({"queued": queued} if queued else {}), "at": NOW - timedelta(minutes=ago)})
        # Round 1 traded in: Player 01 x3, then Player 02..12 once each (12 players: the list stops at 10). Out: 07 x3, 06 x1.
        for k in "ABC":
            await tx(k, 1, "transfer_in", 1); await tx(k, 1, "transfer_out", 7)
        await tx("A", 1, "transfer_out", 6)
        for i in range(2, 13):
            await tx("A", 1, "transfer_in", i)
        for _ in range(5):
            await tx("X", 1, "transfer_in", 1)             # another club's team: must not count
        # Round 2: a queued transfer q2 applied (counts), and q1 applied then taken back when the round was unsettled (does not).
        await tx("A", 2, "transfer_in", 4, queued="q1", ago=60); await tx("A", 2, "transfer_out", 5, queued="q1", ago=60)
        await tx("A", 2, "transfer_undone", 4, queued="q1", ago=30)
        await tx("B", 2, "transfer_in", 4, queued="q2", ago=20); await tx("B", 2, "transfer_out", 5, queued="q2", ago=20)
        # Round 3 (open): Player 08 in x2, Player 01 out x2.
        await tx("A", 3, "transfer_in", 8); await tx("B", 3, "transfer_in", 8)
        await tx("A", 3, "transfer_out", 1); await tx("B", 3, "transfer_out", 1)
        await s.commit()


async def _async(v):
    return v


async def insights(round_=None):
    fn = getattr(public_fantasy, "round_insights", None)
    if fn is None:
        return None
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        public_fantasy._club_for_token = lambda db, token: _async(org)
        return await fn(token="t", round=round_, db=s)


async def set_status(n, status):
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET status=:st WHERE id=:i"), {"st": status, "i": RID[n]})
        await s.commit()


def nm(rows):
    return [r["name"] for r in rows]


async def main() -> int:
    await build_schema()
    await seed()

    print("1. which rounds are offered")
    res = await insights()
    check("GET round-insights exists", res is not None, "route missing")
    opts = (res or {}).get("rounds", [])
    check("scored rounds 1 and 2 plus the open round 3; later and unsettled rounds are not offered",
          [(o["number"], o["status"]) for o in opts] == [(1, "scored"), (2, "scored"), (3, "live")], str(opts))
    check("with no round given it opens on the latest scored round", (res or {}).get("selected") and res["selected"]["number"] == 2)

    print("2. top scorers (round 1)")
    r1 = ((await insights(1)) or {}).get("selected") or {}
    top = r1.get("top_scorers", [])
    check("highest first, and only the top 10 of the 12 who played", len(top) == 10 and top[0]["points"] == 120 and top[1]["points"] == 100, str(top[:2]))
    check("the scorers are 120, 100, 80, six on 60 (name order) and 40; the 20 and the 0 are cut",
          [t["points"] for t in top] == [120, 100, 80, 60, 60, 60, 60, 60, 60, 40], str([t["points"] for t in top]))
    check("a player who did not play is left out", "Player 13" not in nm(top))
    check("a name an admin set is the name shown", "Nick Name" in nm(top) and "Player 02" not in nm(top))
    check("picked_by counts the teams that locked the player (Player 01 in two, Player 03 in one)",
          top and top[0]["picked_by"] == 2 and next(t for t in top if t["name"] == "Player 03")["picked_by"] == 1, str(top[:3]))

    print("3. most traded in and out")
    tin = r1.get("traded_in", [])
    check("traded in: Player 01 leads on 3 and the list stops at 10", len(tin) == 10 and tin[0]["name"] == "Player 01" and tin[0]["count"] == 3, str(tin[:2]))
    check("another club's team trading Player 01 is not counted (3, not 8)", tin and tin[0]["count"] == 3)
    check("Player 11 and 12 (once each, after the cut) are not listed", not {"Player 11", "Player 12"} & set(nm(tin)))
    tout = r1.get("traded_out", [])
    check("traded out: Player 07 x3 then Player 06 x1", [(t["name"], t["count"]) for t in tout] == [("Player 07", 3), ("Player 06", 1)], str(tout))
    r2 = ((await insights(2)) or {}).get("selected") or {}
    async with Session() as s:
        n_undone = (await s.execute(text("SELECT COUNT(*) FROM fantasy_transactions WHERE type='transfer_undone'"))).scalar()
        n_q1 = (await s.execute(text("SELECT COUNT(*) FROM fantasy_transactions WHERE detail->>'queued'='q1' AND type='transfer_in'"))).scalar()
    check("(the taken-back transfer's rows exist)", n_undone == 1 and n_q1 == 1)
    check("round 2 traded in: Player 04 once (q2), the undone q1 is not counted", [(t["name"], t["count"]) for t in r2.get("traded_in", [])] == [("Player 04", 1)], str(r2.get("traded_in")))
    check("round 2 traded out: Player 05 once", [(t["name"], t["count"]) for t in r2.get("traded_out", [])] == [("Player 05", 1)], str(r2.get("traded_out")))

    print("4. price risers and fallers")
    check("round 1 risers: 01 +0.3, Nick Name +0.2, 03 +0.1, on 8.3, 8.2, 8.1",
          [(r["name"], r["move"], r["price"]) for r in r1.get("risers", [])] == [("Player 01", 0.3, 8.3), ("Nick Name", 0.2, 8.2), ("Player 03", 0.1, 8.1)], str(r1.get("risers")))
    check("round 1 fallers: 07 -0.3, 06 -0.2, 05 -0.1",
          [(r["name"], r["move"]) for r in r1.get("fallers", [])] == [("Player 07", -0.3), ("Player 06", -0.2), ("Player 05", -0.1)], str(r1.get("fallers")))
    check("round 2's biggest riser is Player 07 (the 150 day)", r2.get("risers") and r2["risers"][0]["name"] == "Player 07", str(r2.get("risers")))
    check("round 2 does not repeat round 1's risers (Player 01 had +0.3 then)", "Player 01" not in nm(r2.get("risers", [])))
    check("risers are biggest first and fallers are most negative first",
          all(a["move"] >= b["move"] for a, b in zip(r2.get("risers", []), r2.get("risers", [])[1:]))
          and all(a["move"] <= b["move"] for a, b in zip(r2.get("fallers", []), r2.get("fallers", [])[1:])))

    print("5. the open round shows trades and no points")
    r3 = ((await insights(3)) or {}).get("selected") or {}
    check("round 3 trades are in: Player 08 in x2, Player 01 out x2",
          [(t["name"], t["count"]) for t in r3.get("traded_in", [])] == [("Player 08", 2)] and [(t["name"], t["count"]) for t in r3.get("traded_out", [])] == [("Player 01", 2)], str(r3))
    check("... with no points and no price moves yet", r3 and r3["top_scorers"] == [] and r3["risers"] == [] and r3["fallers"] == [] and r3["status"] == "live")
    check("the teams count is the club-wide league's (3)", r3.get("teams") == 3, str(r3.get("teams")))

    print("6. rounds that are not offered")
    for n_ in (4, 5, 99):
        try:
            got = await insights(n_)
            code = 200 if got is not None else "missing"
        except HTTPException as e:
            code = e.status_code
        check(f"round {n_} is a 404", code == 404, str(code))

    print("7. derived on read")
    await set_status(2, "unsettled")
    res = await insights()
    check("unsettling round 2 drops it, and round 2 becomes the open round with no points",
          res and [(o["number"], o["status"]) for o in res["rounds"]] == [(1, "scored"), (2, "live")], str(res and res["rounds"]))
    check("the default round falls back to round 1", res and res["selected"]["number"] == 1)
    await set_status(2, "scored")

    print("8. a club with no league")
    async with Session() as s:
        await s.execute(text("DELETE FROM fantasy_leagues WHERE id=:i"), {"i": LEAGUE})
        await s.commit()
    res = await insights()
    check("returns empty, not an error", res and res["rounds"] == [] and res["selected"] is None, str(res))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
