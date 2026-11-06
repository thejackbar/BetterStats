"""Milestone watch for BetterSocials lineups (services/social_milestones.py).

    DATABASE_URL=postgresql+asyncpg://user:pw@host/verify_social_milestones \
        python backend/verification/verify_social_milestones.py

Runs the SHIPPED service against a real Postgres with the real schema
(`Base.metadata.create_all`) and the real `v_effective_*` views, so the career
figures are `milestone_totals.profile_totals` and not a stand-in. Run on its own
database: suites that share one collide on stub tables.

Asserted:
- a player on 99 club games who is in the XI is a CERTAIN milestone and outranks
  a nearer runs milestone of their own; one item per player; three at most;
- after "certain", the order is how far through its own window a candidate is
  (3 of 5 wickets beats 30 of 50 runs only on the raw gap tie-break);
- a badge is per player (more of them than the strip lists);
- thresholds follow the club's increments (runs every 250 reads "20 runs to 250");
- a match already scored is not counted twice (the 100th stays the 100th);
- a player of another club, or an id nobody holds, is not `known` and gets nothing;
- freshness: an UPCOMING game dated before today is `stale`; a last sync that
  finished before the last scored game's day is `stale`; a sync after it is `fresh`;
  no sync history is `unknown` (and not stale); a game still to be played, or one
  called off, never makes it stale.

SM_PATH=<a mutated copy of the service> is the control run. A control must FAIL the
checks it breaks and report, never crash: every read goes through `get`.
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base
from app.services.superseded_ddl import STATEMENTS as SUPERSEDED_DDL

SPEC = importlib.util.spec_from_file_location(
    "social_milestones_under_test",
    os.environ.get("SM_PATH") or str(HERE.parent / "app" / "services" / "social_milestones.py"))
sm = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sm)

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
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


TODAY = date.today()
MATCH_DAY = TODAY + timedelta(days=5)
YEAR = TODAY.year
ORG, OTHER = uuid.uuid4(), uuid.uuid4()
SEASON, GRADE = uuid.uuid4(), uuid.uuid4()
O_SEASON, O_GRADE = uuid.uuid4(), uuid.uuid4()
P = {k: uuid.uuid4() for k in ("GAMES", "BOTH", "WKT", "RUNS2", "RUNS", "FAR", "COUNTED", "ELSEWHERE", "C250")}


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS grade_merge_logs (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(),
                org_id UUID NOT NULL, canonical_name TEXT NOT NULL,
                alias_name TEXT NOT NULL, undone_at TIMESTAMPTZ)"""))
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS season_aliases (
                id SERIAL PRIMARY KEY, merged_at TIMESTAMPTZ DEFAULT NOW(), org_id UUID NOT NULL,
                canonical_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                alias_season_id UUID NOT NULL REFERENCES seasons(id) ON DELETE CASCADE,
                undone_at TIMESTAMPTZ)"""))
        await conn.execute(text(
            "ALTER TABLE organisations ADD COLUMN IF NOT EXISTS amalgamate_seasons BOOLEAN NOT NULL DEFAULT false"))
        for name, sql in view_statements():
            await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
            await conn.execute(text(sql.replace("OR REPLACE ", "")))
        for stmt in SUPERSEDED_DDL:
            await conn.execute(text(stmt))


async def seed() -> None:
    async with Session() as s:
        async def ex(sql, **kw):
            await s.execute(text(sql), kw)

        for oid, slug in ((ORG, "swt"), (OTHER, "other")):
            await ex("INSERT INTO organisations (id, name, slug, is_active) VALUES (:i, :n, :sl, true)",
                     i=oid, n=slug, sl=f"{slug}-{oid.hex[:8]}")
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s, :o, 'Summer', :y)",
                 s=SEASON, o=ORG, y=YEAR)
        await ex("INSERT INTO grades (id, season_id, name, category, categories) "
                 "VALUES (:g, :s, 'A Grade', 'senior', ARRAY['senior'])", g=GRADE, s=SEASON)
        await ex("INSERT INTO seasons (id, organisation_id, name, year) VALUES (:s, :o, 'Summer', :y)",
                 s=O_SEASON, o=OTHER, y=YEAR)
        await ex("INSERT INTO grades (id, season_id, name, category, categories) "
                 "VALUES (:g, :s, 'B Grade', 'senior', ARRAY['senior'])", g=O_GRADE, s=O_SEASON)
        names = {"GAMES": "Cartwright, Hilton", "BOTH": "Szigligeti, Sam", "WKT": "Wenban, Alex",
                 "RUNS2": "Farmer, Nathan", "RUNS": "Hay, Frazer", "FAR": "Botha, Eric",
                 "COUNTED": "Frame, Josh", "ELSEWHERE": "Stranger, Sid", "C250": "Dallimore, Liam"}
        for k, n in names.items():
            await ex("INSERT INTO players (id, organisation_id, name, is_player, status) "
                     "VALUES (:i, :o, :n, true, 'active')", i=P[k], o=OTHER if k == "ELSEWHERE" else ORG, n=n)

        async def pss(k, **kw):
            cols = {"matches": 0, "runs": 0, "wickets": 0, "catches": 0, "batting_innings": 0}
            cols.update(kw)
            await ex(f"INSERT INTO player_season_stats (player_id, season_id, {', '.join(cols)}) "
                     f"VALUES (:p, :s, {', '.join(':' + c for c in cols)})", p=P[k], s=SEASON, **cols)

        await pss("GAMES", matches=99, runs=980)        # certain 100th, and 20 runs from 1,000
        await pss("BOTH", matches=60, runs=990, wickets=98)    # 10 runs from 1,000, 2 wickets from 100
        await pss("WKT", matches=40, runs=100, wickets=97)     # 3 wickets from 100
        await pss("RUNS2", matches=20, runs=470)        # 30 runs from 500
        await pss("RUNS", matches=30, runs=960)         # 40 runs from 1,000
        await pss("FAR", matches=10, runs=200)
        await pss("COUNTED", matches=100, runs=100)     # 100 including the match already scored
        await pss("ELSEWHERE", matches=99)
        await pss("C250", matches=10, runs=230)         # 20 runs from 250 only under runs-every-250
        await s.commit()


async def put_game(status: str, day: date, home=ORG, players=()) -> uuid.UUID:
    gid = uuid.uuid4()
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO games (id, grade_id, played_at, home_team, away_team, home_org_id, status) "
            "VALUES (:i, :g, :d, 'Us', 'Them', :h, :st)"),
            {"i": gid, "g": GRADE if home == ORG else O_GRADE, "d": day, "h": home, "st": status})
        for p in players:
            await s.execute(text("INSERT INTO game_appearances (game_id, player_id) VALUES (:g, :p)"),
                            {"g": gid, "p": p})
        await s.commit()
    return gid


async def clear_games_and_syncs() -> None:
    async with Session() as s:
        await s.execute(text("DELETE FROM game_appearances"))
        await s.execute(text("DELETE FROM games"))
        await s.execute(text("DELETE FROM sync_runs"))
        await s.commit()


async def put_sync(done: datetime, status: str = "success") -> None:
    async with Session() as s:
        await s.execute(text(
            "INSERT INTO sync_runs (id, org_id, kind, status, started_at, updated_at, completed_at, stats) "
            "VALUES (:i, :o, 'org_full', :st, :d, :d, :d, '{}'::jsonb)"),
            {"i": uuid.uuid4(), "o": ORG, "st": status, "d": done})
        await s.commit()


async def ask(ids, on=MATCH_DAY):
    async with Session() as s:
        return await sm.social_milestones(s, SimpleNamespace(id=ORG), [str(i) for i in ids], on, today=TODAY)


def get(d, *path, default=None):
    cur = d
    for k in path:
        if isinstance(cur, dict) and k in cur:
            cur = cur[k]
        else:
            return default
    return cur


async def main() -> None:
    await build_schema()
    await seed()
    squad = [P[k] for k in ("GAMES", "BOTH", "WKT", "RUNS2", "RUNS", "FAR", "ELSEWHERE")]

    print("\n── ranking, one per player, three at most ──")
    out = await ask(squad)
    items = get(out, "items", default=[])
    who = {str(v): k for k, v in P.items()}
    got = [(who.get(i.get("player_id")), i.get("kind"), i.get("needed")) for i in items]
    print("   items:", got)
    check("three items at most", len(items) == 3, str(len(items)))
    check("the certain 100th game is first", got[:1] == [("GAMES", "games", 1)], str(got))
    check("a player with two candidates takes only their closest (BOTH: runs 10/50)",
          ("BOTH", "runs", 10) in got and [g for g in got if g[0] == "BOTH"] == [("BOTH", "runs", 10)], str(got))
    check("a tie on window share goes to the smaller raw gap (3 wickets before 30 runs)",
          got[2:3] == [("WKT", "wickets", 3)], str(got))
    check("the fourth and fifth are cut from the strip (RUNS2 and RUNS)",
          not any(g[0] in ("RUNS2", "RUNS") for g in got), str(got))
    check("games label reads as the spec says", "100th club game" in [i.get("label") for i in items], str([i.get("label") for i in items]))
    check("runs label reads 'X runs to 1,000 club runs'", "10 runs to 1,000 club runs" in [i.get("label") for i in items])
    check("wickets label reads 'X wickets to 100 club wickets'", "3 wickets to 100 club wickets" in [i.get("label") for i in items])
    badges = get(out, "badges", default={})
    check("a badge for every player in reach (five), more than the strip lists",
          sorted(who.get(k) for k in badges) == sorted(["GAMES", "BOTH", "WKT", "RUNS2", "RUNS"]),
          str(sorted(who.get(k) for k in badges)))
    check("a player far from anything has no badge", str(P["FAR"]) not in badges)
    check("a player of another club is not known and has no badge",
          str(P["ELSEWHERE"]) not in get(out, "known", default=[]) and str(P["ELSEWHERE"]) not in badges)
    check("an id nobody holds is simply not known", str(uuid.uuid4()) not in get(out, "known", default=[]))

    print("\n── a match already scored is not counted twice ──")
    await put_game("COMPLETED", MATCH_DAY, players=[P["COUNTED"]])
    out = await ask([P["COUNTED"]])
    got = [(who.get(i.get("player_id")), i.get("kind"), i.get("current")) for i in get(out, "items", default=[])]
    check("the 100th game is still the 100th once the match is in the figures (99 before it)",
          got == [("COUNTED", "games", 99)], str(got))
    await clear_games_and_syncs()
    out = await ask([P["COUNTED"]])
    got = [(i.get("kind")) for i in get(out, "items", default=[])]
    check("control: with no scored match on the day the same player is on 100, nothing certain",
          "games" not in got, str(got))

    print("\n── the club's own increments ──")
    out = await ask([P["C250"]])
    check("default scheme: 230 runs is not near anything", get(out, "items", default=[]) == [], str(get(out, "items")))
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET milestone_runs_step = 250 WHERE id = :o"), {"o": ORG})
        await s.commit()
    out = await ask([P["C250"]])
    labels = [i.get("label") for i in get(out, "items", default=[])]
    check("runs every 250: '20 runs to 250 club runs'", labels == ["20 runs to 250 club runs"], str(labels))
    async with Session() as s:
        await s.execute(text("UPDATE organisations SET milestone_runs_step = NULL WHERE id = :o"), {"o": ORG})
        await s.commit()

    print("\n── freshness: as of the last completed round ──")
    yesterday, last_sat = TODAY - timedelta(days=1), TODAY - timedelta(days=3)
    out = await ask([P["FAR"]])
    check("no games and no syncs: unknown, and NOT stale", get(out, "freshness") == "unknown" and get(out, "stale") is False, str(get(out, "freshness")))
    await put_game("COMPLETED", last_sat)
    out = await ask([P["FAR"]])
    check("a scored game and no sync history: unknown, not stale", get(out, "freshness") == "unknown" and not get(out, "stale"), str(get(out, "freshness")))
    check("as_of names the last scored game's day", get(out, "as_of") == last_sat.isoformat(), str(get(out, "as_of")))
    await put_sync(datetime.combine(last_sat - timedelta(days=2), datetime.min.time(), tzinfo=timezone.utc))
    out = await ask([P["FAR"]])
    check("last sync finished before the last game's day: stale, with a reason",
          get(out, "freshness") == "stale" and get(out, "stale") is True and "sync" in str(get(out, "stale_reason")).lower(), str(get(out, "stale_reason")))
    await put_sync(datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc))
    out = await ask([P["FAR"]])
    check("a sync after the game: fresh", get(out, "freshness") == "fresh" and get(out, "stale") is False, str(get(out, "freshness")))
    await put_sync(datetime.combine(TODAY, datetime.min.time(), tzinfo=timezone.utc), status="error")
    out = await ask([P["FAR"]])
    check("a failed sync never counts as the watermark", get(out, "freshness") == "fresh", str(get(out, "freshness")))
    await put_game("UPCOMING", last_sat)
    out = await ask([P["FAR"]])
    check("a game dated in the past still UPCOMING: stale, even after a sync",
          get(out, "stale") is True and "not scored" in str(get(out, "stale_reason")), str(get(out, "stale_reason")))
    await clear_games_and_syncs()
    await put_sync(datetime.combine(yesterday, datetime.min.time(), tzinfo=timezone.utc))
    await put_game("COMPLETED", last_sat)
    await put_game("UPCOMING", TODAY + timedelta(days=2))
    await put_game("ABANDONED", last_sat - timedelta(days=1))
    out = await ask([P["FAR"]])
    check("a game still to be played, and one called off, never make it stale", get(out, "stale") is False, str(get(out, "stale_reason")))
    await put_game("LIVE", TODAY - timedelta(days=2), home=OTHER)
    out = await ask([P["FAR"]])
    check("another club's game does not make this club stale", get(out, "stale") is False, str(get(out, "stale_reason")))

    print("\n── pure functions ──")
    check("judge_freshness: unknown with nothing to judge by",
          sm.judge_freshness(last_scored=None, unscored=0, synced_at=None)[0] == "unknown")
    check("pick_watch: an empty squad is an empty strip", sm.pick_watch([], None) == [])

    await engine.dispose()
    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
