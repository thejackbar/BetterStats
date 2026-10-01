"""Verification for BetterFantasyCricket round generation, against a real Postgres.

Reported: "Generate rounds" on a brand-new 2026/27 fantasy season answers
"Generated 0 rounds" and the admin was told to run a BetterSelect fixtures sync
first. Cause: `generate_rounds` read only STORED games (`v_effective_games`), and
a new season has none until its matches are played and synced; upcoming fixtures
are never stored in `games`.

This runs the SHIPPED `services/fantasy_engine.generate_rounds`, the shipped
`routers/fantasy.generate_rounds` and `create_season` route bodies, over the
`v_effective_*` views pulled out of the migrations. Only the Play-Cricket network
call (`grassroots_scores_client.get_grade_matches`) is replaced, with a draw
whose shape is the real `/scores/grades/{id}/matches` payload.

CONTROL: the previous commit's engine (`git show HEAD:...`) is loaded as a
module and run over the same seed. It must fail on exactly the reported
behaviour (zero rounds with a published draw), read through presence-safe
accessors so a different failure shows as a different message, not a crash.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_rounds.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import (
    Base, Organisation, Season, Grade, Game, FantasySeason, FantasyRound,
)
from app.services import grassroots_scores_client as gr
from app.services import playhq_client
from app.services import fantasy_engine
from app.routers import fantasy as fantasy_router

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
        print(f"  FAIL {label}{('  - ' + detail) if detail else ''}")


ORG = uuid.uuid4()
OTHER_ORG = uuid.uuid4()
S_NEW = uuid.uuid4()          # 2026 season, no games stored
G_NEW = uuid.uuid4()
GUID_NEW = "ca-grade-guid-2026-a"
S_EMPTY_ORG = uuid.uuid4()
ORG_NO_SEASON = uuid.uuid4()


def match(day: str, home: str, away: str, status: int, home_org=None, away_org=None, time="13:00:00"):
    """A `/scores/grades/{id}/matches` row, trimmed to the fields the engine reads."""
    return {
        "id": str(uuid.uuid4()), "statusId": status,
        "matchSchedule": [{"startDateTime": f"{day}T{time}"}],
        "round": {"name": "Round"}, "venue": {"name": "Oval"},
        "teams": [
            {"isHome": True, "displayName": home, "owningOrganisation": {"id": home_org}},
            {"isHome": False, "displayName": away, "owningOrganisation": {"id": away_org}},
        ],
    }


# Draw for the club's new-season grade. Weeks (ISO): Oct 3 completed (week 40),
# Oct 10 (41), Sat Oct 17 + Sun Oct 18 (42, ONE round), Oct 24 (43). Oct 31 is two
# OTHER clubs, so it must not make a round. Oct 7 is a midweek abandoned match of
# ours (still a date the club was meant to play, so it joins week 41).
DRAW = [
    match("2026-10-03", "LCC Firsts", "Rovers", 3, str(ORG)),
    match("2026-10-10", "Rovers", "LCC Firsts", 0, None, str(ORG)),
    match("2026-10-17", "LCC Firsts", "Tigers", 0, str(ORG)),
    match("2026-10-18", "Lions", "LCC Firsts", 0, None, str(ORG)),
    match("2026-10-24", "LCC Firsts", "Eagles", 0, str(ORG)),
    match("2026-10-31", "Sharks", "Kings", 0, str(OTHER_ORG), str(OTHER_ORG)),
    match("2026-10-07", "LCC Firsts", "Casuals", 4, str(ORG)),
]

FETCH_LOG: list[tuple[str, bool]] = []


async def fake_get_grade_matches(grade_id: str, *, force: bool = False):
    FETCH_LOG.append((grade_id, force))
    return list(DRAW) if grade_id == GUID_NEW else []


UNSYNCED_ORG = uuid.uuid4()    # a club with NOTHING on file for 2026 (not synced since CA published it)
SEASON_LOG: list[str] = []


async def fake_get_seasons(org_id: str):
    SEASON_LOG.append(org_id)
    if org_id == str(UNSYNCED_ORG):
        return [
            {"id": "ca-season-2025", "name": "Summer 2025/26", "startDate": "2025-10-01"},
            {"id": "ca-season-2026", "name": "Summer 2026/27", "startDate": "2026-10-01"},
        ]
    return []


async def fake_get_teams(org_id: str, season_id: str):
    # Only the 2026 season is asked for; a 2025 request would be a bug.
    assert season_id == "ca-season-2026", season_id
    return [{"id": "t1", "grades": [{"id": GUID_NEW, "name": "Firsts"}]},
            {"id": "t2", "grade": {"id": GUID_NEW, "name": "Firsts"}}]


async def build_schema() -> None:
    async with engine.begin() as conn:
        # drop_all cannot order organisations <-> users (circular FK); reset the schema.
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        # Migration 087 gives every fantasy table a server-side id default and the
        # engine's raw INSERTs rely on it; create_all only sets a Python-side one.
        for (tbl,) in (await conn.execute(text(
                "SELECT table_name FROM information_schema.columns WHERE table_schema='public' "
                "AND column_name='id' AND table_name LIKE 'fantasy\\_%' AND data_type='uuid'"))).all():
            await conn.execute(text(f'ALTER TABLE "{tbl}" ALTER COLUMN id SET DEFAULT gen_random_uuid()'))
        json_cols = (await conn.execute(text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = 'public' AND data_type = 'json'"))).all()
        for tbl, col in json_cols:
            await conn.execute(text(
                f'ALTER TABLE "{tbl}" ALTER COLUMN "{col}" TYPE jsonb USING "{col}"::text::jsonb'))
        from app.services.competition_ddl import STATEMENTS as _COMP_DDL
        for _stmt in _COMP_DDL:
            await conn.execute(text(_stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        s.add_all([
            Organisation(id=ORG, name="LCC Cricket Club", short_name="LCC", slug="lcc", is_active=True),
            Organisation(id=ORG_NO_SEASON, name="Bare Cricket Club", slug="bare", is_active=True),
        ])
        await s.flush()
        s.add(Season(id=S_NEW, organisation_id=ORG, name="Summer 2026/27", year=2026, grassroots_id="s-2026"))
        await s.flush()
        s.add(Grade(id=G_NEW, season_id=S_NEW, name="Firsts", grassroots_id=GUID_NEW))
        await s.commit()


async def season(year: int, org=ORG, **kw) -> FantasySeason:
    async with Session() as s:
        fs = FantasySeason(organisation_id=org, season_year=year, name=f"{year}/{(year + 1) % 100:02d} Fantasy",
                           status="setup", scoring={}, rules={}, **kw)
        s.add(fs)
        await s.commit()
        return fs


async def rounds_of(fs_id) -> list[FantasyRound]:
    async with Session() as s:
        return list((await s.execute(
            select(FantasyRound).where(FantasyRound.fantasy_season_id == fs_id)
            .order_by(FantasyRound.round_number))).scalars())


def _count(res) -> object:
    """Presence-safe: the shipped engine returns a dict, the control returns an int."""
    if isinstance(res, dict):
        return res.get("rounds", "<no 'rounds' key>")
    return res


async def run_control() -> int:
    """The previous commit's engine over the same seed. Must show 0 rounds."""
    src = subprocess.check_output(
        ["git", "show", "HEAD:backend/app/services/fantasy_engine.py"],
        cwd=Path(__file__).resolve().parent.parent.parent, text=True)
    tmp = Path(__file__).resolve().parent / "_fantasy_engine_control.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("fantasy_engine_control", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fs = await season(2026)
        async with Session() as s:
            fs = await s.get(FantasySeason, fs.id)
            n = _count(await mod.generate_rounds(s, fs))
            await s.commit()
        print(f"CONTROL (previous commit): generate_rounds -> {n!r} rounds for a published draw")
        check("control reproduces the report: zero rounds with a published draw", n == 0, f"got {n!r}")
        return 0 if FAIL == 0 else 1
    finally:
        tmp.unlink(missing_ok=True)


async def main() -> int:
    await build_schema()
    await seed()
    gr.get_grade_matches = fake_get_grade_matches
    playhq_client.get_seasons = fake_get_seasons
    playhq_client.get_teams = fake_get_teams

    if "--control" in sys.argv:
        return await run_control()

    print("1. A new season with a published draw and NO stored games")
    fs = await season(2026)
    async with Session() as s:
        fs = await s.get(FantasySeason, fs.id)
        res = await fantasy_engine.generate_rounds(s, fs)
        await s.commit()
    rs = await rounds_of(fs.id)
    check("four rounds generated from the draw", len(rs) == 4, f"got {len(rs)}")
    check("result reports four rounds", res.get("rounds") == 4, repr(res))
    check("detail sentence names the count and the season", "4 rounds" in res.get("detail", "") and "2026/27" in res.get("detail", ""), res.get("detail", ""))
    check("round windows follow the draw",
          [(r.start_date, r.end_date) for r in rs] == [
              (date(2026, 10, 3), date(2026, 10, 3)),
              (date(2026, 10, 7), date(2026, 10, 10)),
              (date(2026, 10, 17), date(2026, 10, 18)),
              (date(2026, 10, 24), date(2026, 10, 24))],
          repr([(r.start_date, r.end_date) for r in rs]))
    check("Sat + Sun of one weekend are ONE round", rs[2].start_date == date(2026, 10, 17) and rs[2].end_date == date(2026, 10, 18))
    check("another club's fixture (Oct 31) makes no round", all(r.end_date != date(2026, 10, 31) for r in rs))
    check("our own abandoned midweek match (Oct 7) is still counted, in the week it falls", rs[1].start_date == date(2026, 10, 7))
    check("rounds start as 'upcoming'", all(r.status == "upcoming" for r in rs))

    print("2. Idempotent, and a scored round is never rewritten")
    async with Session() as s:
        await s.execute(text("UPDATE fantasy_rounds SET status='scored', name='Round 1 (settled)' WHERE id = :i"), {"i": rs[0].id})
        await s.commit()
    async with Session() as s:
        fs2 = await s.get(FantasySeason, fs.id)
        await fantasy_engine.generate_rounds(s, fs2)
        await s.commit()
    rs2 = await rounds_of(fs.id)
    check("still four rounds after a re-run", len(rs2) == 4, f"got {len(rs2)}")
    check("scored round untouched", rs2[0].status == "scored" and rs2[0].name == "Round 1 (settled)")

    print("3. Stored games merge with the calendar (union, no double count)")
    fs_b = await season(2025)   # a 2025 season: stored games only, calendar has no 2025 grades
    async with Session() as s:
        s25 = Season(id=uuid.uuid4(), organisation_id=ORG, name="Summer 2025/26", year=2025)
        s.add(s25)
        await s.flush()
        g25 = Grade(id=uuid.uuid4(), season_id=s25.id, name="Seconds")
        s.add(g25)
        await s.flush()
        for d in (date(2025, 10, 4), date(2025, 10, 5), date(2025, 10, 18)):
            s.add(Game(id=uuid.uuid4(), grade_id=g25.id, played_at=d, home_team="LCC", away_team="X",
                       home_org_id=ORG, status="COMPLETED"))
        await s.commit()
        fs_b = await s.get(FantasySeason, fs_b.id)
        res = await fantasy_engine.generate_rounds(s, fs_b)
        await s.commit()
    check("stored-only season still works (2 weekends -> 2 rounds)", res.get("rounds") == 2, repr(res))
    check("games-only path reports from_games=3, from_calendar=0", (res.get("from_games"), res.get("from_calendar")) == (3, 0), repr(res))

    print("4. Zero explains itself")
    fs_e = await season(2027)
    async with Session() as s:
        fs_e = await s.get(FantasySeason, fs_e.id)
        res = await fantasy_engine.generate_rounds(s, fs_e)
    check("club has no 2027/28 season anywhere: zero + plain reason", res.get("rounds") == 0 and "lists no 2027/28 season" in res.get("detail", ""), repr(res))
    async with Session() as s:
        s2 = Season(id=uuid.uuid4(), organisation_id=ORG, name="Summer 2028/29", year=2028)
        s.add(s2)
        await s.flush()
        s.add(Grade(id=uuid.uuid4(), season_id=s2.id, name="Thirds", grassroots_id="ca-grade-empty"))
        await s.commit()
    fs_g = await season(2028)
    async with Session() as s:
        fs_g = await s.get(FantasySeason, fs_g.id)
        res = await fantasy_engine.generate_rounds(s, fs_g)
    check("grades exist but draw unpublished: zero + 'try again' reason",
          res.get("rounds") == 0 and "no matches published" in res.get("detail", ""), repr(res))

    print("4b. Nothing synced for the year: grades are discovered live (no sync, no BetterSelect)")
    async with Session() as s:
        s.add(Organisation(id=UNSYNCED_ORG, name="Unsynced Cricket Club", short_name="LCC", slug="unsynced", is_active=True))
        await s.commit()
    fs_u = await season(2026, org=UNSYNCED_ORG)
    SEASON_LOG.clear()
    async with Session() as s:
        fs_u = await s.get(FantasySeason, fs_u.id)
        res = await fantasy_engine.generate_rounds(s, fs_u)
        await s.commit()
    check("club with no 2026 season/grades on file still gets its 4 rounds", res.get("rounds") == 4, repr(res))
    check("discovery asked Play-Cricket for that org's season list exactly once", SEASON_LOG == [str(UNSYNCED_ORG)], repr(SEASON_LOG))
    SEASON_LOG.clear()
    async with Session() as s:
        fs3 = await s.get(FantasySeason, fs.id)
        await fantasy_engine.generate_rounds(s, fs3)
    check("...(checked) synced club made no discovery call", SEASON_LOG == [], repr(SEASON_LOG))

    print("5. Shipped route bodies")
    FETCH_LOG.clear()
    fs_r = await season(2026, org=ORG_NO_SEASON)   # org with no grades at all
    async with Session() as s:
        org = await s.get(Organisation, ORG)
        out = await fantasy_router.create_season(
            fantasy_router.SeasonCreate(season_year=2026), club=org, db=s, _=None)
    check("create_season does not duplicate an existing 2026 season", out.get("created") is False, repr(out)[:120])
    ORG2 = uuid.uuid4()
    async with Session() as s:
        s.add(Organisation(id=ORG2, name="LCC Juniors Cricket Club", short_name="LCC", slug="lccj", is_active=True))
        await s.flush()
        sx = Season(id=uuid.uuid4(), organisation_id=ORG2, name="Summer 2026/27", year=2026)
        s.add(sx)
        await s.flush()
        s.add(Grade(id=uuid.uuid4(), season_id=sx.id, name="U12", grassroots_id=GUID_NEW))
        await s.commit()
    async with Session() as s:
        org2 = await s.get(Organisation, ORG2)
        out = await fantasy_router.create_season(
            fantasy_router.SeasonCreate(season_year=2026), club=org2, db=s, _=None)
    new_id = out["season"]["id"]
    rs_new = await rounds_of(uuid.UUID(new_id))
    check("create_season creates the season AND its rounds with no extra click", out.get("created") is True and len(rs_new) == 4, f"created={out.get('created')} rounds={len(rs_new)}")
    FETCH_LOG.clear()
    async with Session() as s:
        org2 = await s.get(Organisation, ORG2)
        body = await fantasy_router.generate_rounds(new_id, club=org2, db=s, _=None)
    check("route returns rounds + detail for the screen", body.get("rounds") == 4 and "detail" in body, repr(body))
    check("admin click bypasses the cache (force=True), one fetch per grade", FETCH_LOG == [(GUID_NEW, True)], repr(FETCH_LOG))

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
