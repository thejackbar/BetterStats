"""Round-by-round rankings and round winners for Fantasy, against Postgres.

Asked: rankings for each round so the club can see who won each one, and the same for rounds already played
so they can be walked through round by round.

Drives the SHIPPED route bodies (`public_fantasy.round_winners`, `public_fantasy.round_ranking`,
`fantasy.round_winners` for the admin) and `services/fantasy_round_rank` over a real database. Only the club
lookup and the session cookie read are stubbed.

Pinned here:
  * Every round already scored is ranked from the stored squad round rows, with nothing to backfill.
  * A tie for first is a shared win, ranks skip after a tie (1, 1, 3), a round topped on 0 has no winner.
  * Upcoming, running and unsettled rounds are not ranked (each paired with a check that its rows exist).
  * A team is ranked only in rounds it had joined and fielded a team in; another league's teams never appear.
  * Derived on read: a corrected score changes the winner, unsettling a round removes it, settling restores it.

CONTROL: the routes do not exist before this change, so against the previous commit every route check
reports the route as missing instead of crashing.

Run, on its own database:
  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_round_rank.py
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
    Base, FantasyLeague, FantasyManager, FantasyRound, FantasySeason, FantasySquad, Organisation,
)
from app.routers import public_fantasy

try:
    from app.services.competition_ddl import STATEMENTS as COMP_STATEMENTS
except ImportError:  # pragma: no cover
    COMP_STATEMENTS = []

try:
    from app.services import fantasy_round_rank
except ImportError:  # the control run: the module does not exist yet
    fantasy_round_rank = None

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
RID = {n: uuid.uuid4() for n in range(1, 8)}
RID2 = uuid.uuid4()
MGR = {k: uuid.uuid4() for k in "ABCDEX"}
SQ = {k: uuid.uuid4() for k in "ABCDEX"}
LEAGUE, LEAGUE2, MINI = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
VIEWER = {"id": None}


def lineup(pts):
    return [{"player_id": str(uuid.uuid4()), "role": "batter", "points": pts, "eff_points": pts, "counted": True}]


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


# round number -> status. 1,2,3 and 6 scored; 4 upcoming; 5 unsettled; 7 scored but nobody scored.
STATUS = {1: "scored", 2: "scored", 3: "scored", 4: "upcoming", 5: "unsettled", 6: "scored", 7: "scored"}


async def seed() -> None:
    async with Session() as s:
        s.add_all([Organisation(id=ORG, name="Applecross", slug="apx", is_active=True),
                   Organisation(id=ORG2, name="Other CC", slug="other", is_active=True)])
        await s.flush()
        s.add_all([
            FantasySeason(id=FS_ID, organisation_id=ORG, season_year=TODAY.year, name="Fantasy", status="active", scoring={}, rules={}),
            FantasySeason(id=FS2, organisation_id=ORG2, season_year=TODAY.year, name="Other", status="active", scoring={}, rules={}),
        ])
        await s.flush()
        for n, st in STATUS.items():
            s.add(FantasyRound(id=RID[n], fantasy_season_id=FS_ID, organisation_id=ORG, round_number=n, name=f"Round {n}", status=st,
                               start_date=TODAY - timedelta(days=70 - n * 7), end_date=TODAY - timedelta(days=69 - n * 7),
                               lock_at=NOW - timedelta(days=70 - n * 7)))
        s.add(FantasyRound(id=RID2, fantasy_season_id=FS2, organisation_id=ORG2, round_number=1, name="Round 1", status="scored",
                           start_date=TODAY - timedelta(days=20), end_date=TODAY - timedelta(days=19), lock_at=NOW - timedelta(days=20)))
        s.add_all([
            FantasyLeague(id=LEAGUE, fantasy_season_id=FS_ID, organisation_id=ORG, kind="global_salary_cap", name="Club ladder"),
            FantasyLeague(id=MINI, fantasy_season_id=FS_ID, organisation_id=ORG, kind="mini", name="Mates"),
            FantasyLeague(id=LEAGUE2, fantasy_season_id=FS2, organisation_id=ORG2, kind="global_salary_cap", name="Other ladder"),
        ])
        for k in "ABCDEX":
            s.add(FantasyManager(id=MGR[k], organisation_id=ORG if k != "X" else ORG2, display_name=f"Manager {k}"))
        await s.flush()
        # D joined at round 3. E never fielded a team. X is another club's.
        for k, jr in (("A", None), ("B", None), ("C", None), ("D", 3), ("E", None)):
            s.add(FantasySquad(id=SQ[k], fantasy_season_id=FS_ID, league_id=LEAGUE, manager_id=MGR[k], organisation_id=ORG,
                               team_name=f"Team {k}", free_transfers=1, joined_round=jr))
        s.add(FantasySquad(id=SQ["X"], fantasy_season_id=FS2, league_id=LEAGUE2, manager_id=MGR["X"], organisation_id=ORG2,
                           team_name="Team X", free_transfers=1))
        await s.commit()
    async with Session() as s:
        async def srs(k, rid, points, lu=True, chip=None, hit=0):
            await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, transfer_hit, lineup, chip_used) "
                                 "VALUES (:s, :r, :p, :p, :h, CAST(:l AS JSONB), :c)"),
                            {"s": SQ[k], "r": rid, "p": points, "h": hit, "l": json.dumps(lineup(points) if lu else []), "c": chip})
        # Round 1: B 20 wins; A 5. D has a stale row from before they joined, E has a chip tally and no team.
        await srs("A", RID[1], 5); await srs("B", RID[1], 20); await srs("C", RID[1], 12)
        await srs("D", RID[1], 99)
        await srs("E", RID[1], 0, lu=False, chip="wildcard")
        # Round 2: A and C tie on 30 (shared win), B 10 with a 4 point hit already inside the 10.
        await srs("A", RID[2], 30, chip="triple_captain"); await srs("C", RID[2], 30); await srs("B", RID[2], 10, hit=4)
        # Round 3: D (just joined) 40 wins; A and B tie on 12; C fielded a team and scored 0.
        await srs("D", RID[3], 40); await srs("A", RID[3], 12); await srs("B", RID[3], 12); await srs("C", RID[3], 0)
        # Round 4 (upcoming) and round 5 (unsettled) hold rows too: provisional / kept for the manager.
        await srs("A", RID[4], 77); await srs("B", RID[5], 66)
        # Round 6: scored, a different winner from every other round (D takes a second, A a second tie-less).
        await srs("C", RID[6], 50); await srs("D", RID[6], 20)
        # Round 7: scored but every team on 0 points.
        await srs("A", RID[7], 0); await srs("B", RID[7], 0)
        # Another club's team.
        await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup) "
                             "VALUES (:s, :r, 500, 500, CAST(:l AS JSONB))"), {"s": SQ["X"], "r": RID2, "l": json.dumps(lineup(500))})
        await s.commit()


async def _async(v):
    return v


async def call(fn, **kw):
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        public_fantasy._club_for_token = lambda db, token: _async(org)
        public_fantasy._read_session = lambda request, club_id: VIEWER["id"]
        return await fn(db=s, **kw)


async def route(name, **kw):
    """Call a shipped public route, or report it missing (the control run)."""
    fn = getattr(public_fantasy, name, None)
    if fn is None:
        return None
    return await call(fn, token="t", request=SimpleNamespace(), **kw)


async def set_status(n, status):
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET status=:st WHERE id=:i"), {"st": status, "i": RID[n]})
        await s.commit()


def names(ws):
    return sorted(w["team_name"] for w in ws)


async def main() -> int:
    await build_schema()
    await seed()
    VIEWER["id"] = MGR["B"]

    print("1. ranking maths")
    if fantasy_round_rank is None:
        check("services.fantasy_round_rank exists", False, "module missing")
    else:
        rk = fantasy_round_rank.rank_round([
            {"squad_id": "a", "team_name": "A", "points": 10}, {"squad_id": "b", "team_name": "B", "points": 30},
            {"squad_id": "c", "team_name": "C", "points": 30}, {"squad_id": "d", "team_name": "D", "points": 5}])
        check("ties share a rank and the next rank skips (1, 1, 3, 4)", [r["rank"] for r in rk] == [1, 1, 3, 4], str([r["rank"] for r in rk]))
        check("both teams on the top score are marked winners", [r["winner"] for r in rk] == [True, True, False, False])
        zero = fantasy_round_rank.rank_round([{"squad_id": "a", "team_name": "A", "points": 0}, {"squad_id": "b", "team_name": "B", "points": 0}])
        check("a round topped on 0 has no winner", not any(r["winner"] for r in zero))
        check("an empty round ranks to nothing", fantasy_round_rank.rank_round([]) == [])

    print("2. winners across the season (round-winners)")
    res = await route("round_winners")
    check("GET round-winners exists", res is not None, "route missing")
    rounds = {r["number"]: r for r in (res or {}).get("rounds", [])}
    check("scored rounds 1, 2, 3, 6 and 7 are listed, oldest first", [r["number"] for r in (res or {}).get("rounds", [])] == [1, 2, 3, 6, 7],
          str([r["number"] for r in (res or {}).get("rounds", [])]))
    check("round 1 winner is Team B on 20 with a 8 point margin", rounds.get(1) and names(rounds[1]["winners"]) == ["Team B"]
          and rounds[1]["top_points"] == 20 and rounds[1]["margin"] == 8, str(rounds.get(1)))
    check("round 2 is a shared win for Team A and Team C, no margin", rounds.get(2) and names(rounds[2]["winners"]) == ["Team A", "Team C"]
          and rounds[2]["margin"] is None, str(rounds.get(2)))
    check("the winning chip is reported", rounds.get(2) and next(w for w in rounds[2]["winners"] if w["team_name"] == "Team A")["chip"] == "triple_captain")
    check("round 3 winner is Team D, who joined that round", rounds.get(3) and names(rounds[3]["winners"]) == ["Team D"], str(rounds.get(3)))
    check("round 6 winner is Team C", rounds.get(6) and names(rounds[6]["winners"]) == ["Team C"])
    check("round 7 (everyone on 0) has no winner", rounds.get(7) and rounds[7]["winners"] == [] and rounds[7]["margin"] is None, str(rounds.get(7)))
    check("the list view carries no full tables", all("ranking" not in r for r in rounds.values()))
    tally = {t["team_name"]: t for t in (res or {}).get("tally", [])}
    check("tally: Team A 1, B 1, C 2, D 1", {k: v["wins"] for k, v in tally.items()} == {"Team A": 1, "Team B": 1, "Team C": 2, "Team D": 1},
          str({k: v["wins"] for k, v in tally.items()}))
    check("tally is ordered most wins first", (res or {}).get("tally") and res["tally"][0]["team_name"] == "Team C")
    check("the signed-in manager is flagged on their wins", bool(tally.get("Team B", {}).get("you")) and not tally.get("Team C", {}).get("you")
          and rounds.get(1) and rounds[1]["winners"][0].get("you") is True)

    print("3. one round's full table (round-ranking)")
    r1 = await route("round_ranking", round_number=1)
    check("GET round-ranking exists", r1 is not None, "route missing")
    rk1 = (r1 or {}).get("ranking", [])
    check("round 1 table is B 20, C 12, A 5", [(r["team_name"], r["points"]) for r in rk1] == [("Team B", 20.0), ("Team C", 12.0), ("Team A", 5.0)], str(rk1))
    check("a team that joined later is not ranked in a round before it joined (stale row ignored)", "Team D" not in [r["team_name"] for r in rk1])
    check("a team with only a chip tally and no team is not ranked", "Team E" not in [r["team_name"] for r in rk1])
    check("your own row is flagged", [r["team_name"] for r in rk1 if r.get("you")] == ["Team B"])
    r2 = await route("round_ranking", round_number=2)
    rk2 = (r2 or {}).get("ranking", [])
    check("round 2 ranks 1, 1, 3 (A and C level on 30, B on 10)", [r["rank"] for r in rk2] == [1, 1, 3], str(rk2))
    check("the hit is already inside the points and is shown", rk2 and rk2[-1]["points"] == 10.0 and rk2[-1]["transfer_hit"] == 4)
    r3 = await route("round_ranking", round_number=3)
    rk3 = (r3 or {}).get("ranking", [])
    check("round 3 ranks D 1, A and B level 2, C 4 (on 0 but fielded)", [(r["team_name"], r["rank"]) for r in rk3]
          == [("Team D", 1), ("Team A", 2), ("Team B", 2), ("Team C", 4)], str(rk3))
    check("another club's team never appears", all("Team X" not in [r["team_name"] for r in x["ranking"]] for x in (r1, r2, r3) if x))

    print("4. rounds that are not scored are not ranked")
    async with Session() as s:
        n = (await s.execute(text("SELECT COUNT(*) FROM fantasy_squad_round_scores WHERE round_id IN (:a, :b)"), {"a": RID[4], "b": RID[5]})).scalar()
    check("(rows for the upcoming and unsettled rounds do exist)", n == 2, str(n))
    for n_, label in ((4, "upcoming"), (5, "unsettled"), (99, "unknown")):
        try:
            got = await route("round_ranking", round_number=n_)
            code = 200 if got is not None else "missing"
        except HTTPException as e:
            code = e.status_code
        check(f"a {label} round is a 404", code == 404, str(code))
    check("neither appears in the winners list", 4 not in rounds and 5 not in rounds)

    print("5. derived on read: backdating and corrections")
    await set_status(2, "unsettled")
    res = await route("round_winners")
    check("unsettling round 2 takes it out of the list", res and [r["number"] for r in res["rounds"]] == [1, 3, 6, 7], str(res and [r["number"] for r in res["rounds"]]))
    check("... and out of the tally (Team A and C lose that win)", res and {t["team_name"]: t["wins"] for t in res["tally"]} == {"Team B": 1, "Team C": 1, "Team D": 1},
          str(res and res["tally"]))
    await set_status(2, "scored")
    res = await route("round_winners")
    check("settling it again brings it back with no backfill", res and [r["number"] for r in res["rounds"]] == [1, 2, 3, 6, 7])
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_squad_round_scores SET points = 31 WHERE squad_id=:s AND round_id=:r"), {"s": SQ["A"], "r": RID[2]})
        await s.commit()
    res = await route("round_winners")
    rounds = {r["number"]: r for r in (res or {}).get("rounds", [])}
    check("a corrected score moves the winner and gives a margin", bool(rounds.get(2)) and names(rounds[2]["winners"]) == ["Team A"] and rounds[2]["margin"] == 1, str(rounds.get(2)))

    print("6. a signed-out visitor and an empty season")
    VIEWER["id"] = None
    res = await route("round_winners")
    check("a visitor can read the winners, nothing is flagged as theirs", bool(res) and res["my_squad_id"] is None and bool(res["rounds"]) and not any(t["you"] for t in res["tally"]))
    VIEWER["id"] = MGR["B"]
    async with Session() as s:
        await s.execute(text("DELETE FROM fantasy_squad_round_scores"))
        await s.commit()
    res = await route("round_winners")
    check("a season with nothing scored returns empty lists, not an error", res and res["rounds"] == [] and res["tally"] == [], str(res))

    print("7. admin view")
    from app.routers import fantasy as admin
    fn = getattr(admin, "round_winners", None)
    check("admin GET season/{id}/round-winners exists", fn is not None, "route missing")
    if fn is not None:
        await seed_again()
        async with Session() as s:
            org = await s.get(Organisation, ORG)
            out = await fn(season_id=str(FS_ID), club=org, db=s, _=None)
            check("admin sees every scored round with full tables and the tally", [r["number"] for r in out["rounds"]] == [1, 2, 3, 6, 7]
                  and all("ranking" in r for r in out["rounds"]) and out["tally"], str([r["number"] for r in out["rounds"]]))
            try:
                await fn(season_id=str(FS2), club=org, db=s, _=None)
                code = 200
            except HTTPException as e:
                code = e.status_code
            check("another club's season is a 404", code == 404, str(code))

    print(f"\n{PASS} passed, {FAIL} failed")
    await engine.dispose()
    return 1 if FAIL else 0


async def seed_again() -> None:
    """Section 6 emptied the table: put the data back for the admin checks."""
    async with Session() as s:
        async def srs(k, rid, points, lu=True, chip=None):
            await s.execute(text("INSERT INTO fantasy_squad_round_scores (squad_id, round_id, points, raw_points, lineup, chip_used) "
                                 "VALUES (:s, :r, :p, :p, CAST(:l AS JSONB), :c)"),
                            {"s": SQ[k], "r": rid, "p": points, "l": json.dumps(lineup(points) if lu else []), "c": chip})
        await srs("A", RID[1], 5); await srs("B", RID[1], 20)
        await srs("A", RID[2], 30); await srs("C", RID[2], 30)
        await srs("D", RID[3], 40); await srs("A", RID[3], 12)
        await srs("C", RID[6], 50)
        await srs("A", RID[7], 0)
        await s.commit()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
