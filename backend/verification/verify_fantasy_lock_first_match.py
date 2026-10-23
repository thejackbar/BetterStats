"""Verification for the default Fantasy round lock: one hour before the round's first match,
in the club's own timezone, against a real Postgres.

Asked for: "for setting the deadline before closing a game off, take the local time of
the first game of the round and set the deadline to one hour before that game starts.
So for Applecross it should be 24th October, 11am AWST. Write that in for every club."
The default used to be 09:00 Melbourne time on the first game day for every club.

Runs the SHIPPED `services/fantasy_engine.generate_rounds` and the `routers/fantasy`
`list_rounds` and `set_round_lock` bodies over the `v_effective_*` views pulled out of the
migrations. Only the Play-Cricket network call (`get_grade_matches`) is replaced, with a
draw in the real `/scores/grades/{id}/matches` shape.

CONTROL: `--control` runs the engine at git HEAD over the Applecross seed. It must fail on
exactly the reported behaviour (the lock is 09:00 Melbourne, not 11:00 AWST) and on
nothing else.

Run:  DATABASE_URL=postgresql+asyncpg://root@/fantasy_test?host=/var/run/postgresql \
      python verification/verify_fantasy_lock_first_match.py [--control]
"""
from __future__ import annotations

import asyncio
import importlib.util
import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

BACKEND = Path(os.environ.get("BACKEND_DIR") or Path(__file__).resolve().parent.parent)
sys.path.insert(0, str(BACKEND))
sys.path.insert(1, str(Path(__file__).resolve().parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from _view_ddl import view_statements
from app.models.db import Base, Organisation, Season, Grade, Game, FantasySeason, FantasyRound, MarketingClub
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


def at(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def same_instant(a, b) -> bool:
    return a is not None and a == b


def match(day: str, time: str, org, home="Home CC", away="Rovers"):
    return {
        "id": str(uuid.uuid4()), "statusId": 0,
        "matchSchedule": [{"startDateTime": f"{day}T{time}"}],
        "round": {"name": "Round"}, "venue": {"name": "Oval"},
        "teams": [
            {"isHome": True, "displayName": home, "owningOrganisation": {"id": str(org)}},
            {"isHome": False, "displayName": away, "owningOrganisation": {"id": None}},
        ],
    }


APPLECROSS, MELB, NOTIME, NOSTATE, FORCED = (uuid.uuid4() for _ in range(5))
GUID = {o: f"guid-{i}" for i, o in enumerate((APPLECROSS, MELB, NOTIME, NOSTATE, FORCED))}
STATE = {APPLECROSS: "WA", MELB: "VIC", NOTIME: "WA", NOSTATE: None, FORCED: "WA"}

# What the stubbed calendar returns this run, per grade guid. Reassigned between runs.
DRAW: dict[str, list] = {}


def set_draw():
    # Applecross (WA): Sat 24 Oct, A grade at 12:00, a later B grade at 13:30 the same day.
    DRAW[GUID[APPLECROSS]] = [match("2026-10-24", "13:30:00", APPLECROSS), match("2026-10-24", "12:00:00", APPLECROSS),
                              match("2026-10-31", "12:00:00", APPLECROSS)]
    # Melbourne club (VIC, daylight time): 12:00 on 24 Oct is +11:00.
    DRAW[GUID[MELB]] = [match("2026-10-24", "12:00:00", MELB)]
    # A draw that gives dates and no times (midnight): fall back to 09:00 local.
    DRAW[GUID[NOTIME]] = [match("2026-10-24", "00:00:00", NOTIME)]
    DRAW[GUID[NOSTATE]] = [match("2026-10-24", "12:00:00", NOSTATE)]
    DRAW[GUID[FORCED]] = [match("2026-10-24", "12:00:00", FORCED)]


async def fake_get_grade_matches(grade_id: str, *, force: bool = False):
    return list(DRAW.get(grade_id, []))


async def fake_get_seasons(org_id: str):
    return []     # no live discovery: the grades are on file


async def fake_get_teams(org_id: str, season_id: str):
    return []


async def build_schema() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
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
        # The same list alembic 360 and the lifespan run.
        try:
            from app.services.fantasy_first_start_ddl import STATEMENTS as _FS
        except ImportError:
            _FS = []
        for _stmt in _FS:
            await conn.execute(text(_stmt))
        stmts = view_statements()
        for _ in range(2):
            for name, sql in stmts:
                await conn.execute(text(f"DROP VIEW IF EXISTS {name} CASCADE"))
                await conn.execute(text(sql.replace("OR REPLACE ", "")))


async def seed() -> None:
    async with Session() as s:
        for org, name in ((APPLECROSS, "Applecross"), (MELB, "Melbourne Club"), (NOTIME, "No Time Club"),
                          (NOSTATE, "No State Club"), (FORCED, "Forced Zone Club")):
            s.add(Organisation(id=org, name=f"{name} Cricket Club", slug=name.lower().replace(" ", "-"),
                               is_active=True, state=STATE[org]))
        await s.flush()
        for org in GUID:
            sx = Season(id=uuid.uuid4(), organisation_id=org, name="Summer 2026/27", year=2026, grassroots_id=f"s-{org}")
            s.add(sx)
            await s.flush()
            s.add(Grade(id=uuid.uuid4(), season_id=sx.id, name="A Grade", grassroots_id=GUID[org]))
        # The state of a club with none of its own comes from its directory record.
        s.add(MarketingClub(id=uuid.uuid4(), grassroots_guid="mc-nostate", name="No State Cricket Club",
                            state="Western Australia", existing_org_id=NOSTATE))
        await s.commit()


async def season(org, rules=None) -> FantasySeason:
    async with Session() as s:
        fs = FantasySeason(organisation_id=org, season_year=2026, name="2026/27 Fantasy",
                           status="setup", scoring={}, rules=rules or {})
        s.add(fs)
        await s.commit()
        return fs


async def generate(engine_mod, fs_id) -> None:
    async with Session() as s:
        fs = await s.get(FantasySeason, fs_id)
        await engine_mod.generate_rounds(s, fs)
        await s.commit()


async def rounds_of(fs_id) -> list:
    async with Session() as s:
        return list((await s.execute(
            select(FantasyRound).where(FantasyRound.fantasy_season_id == fs_id)
            .order_by(FantasyRound.round_number))).scalars())


def first_start_of(r):
    return getattr(r, "first_start", "<no first_start>")


async def run_control() -> int:
    src = subprocess.check_output(
        ["git", "show", "HEAD:backend/app/services/fantasy_engine.py"],
        cwd=Path(__file__).resolve().parent.parent.parent, text=True)
    tmp = Path(__file__).resolve().parent / "_fantasy_engine_control.py"
    tmp.write_text(src)
    try:
        spec = importlib.util.spec_from_file_location("fantasy_engine_control", tmp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        fs = await season(APPLECROSS)
        await generate(mod, fs.id)
        r = (await rounds_of(fs.id))[0]
        print(f"CONTROL (HEAD engine): Applecross round 1 lock_at = {r.lock_at.isoformat()}")
        check("control: Applecross locks 11:00 AWST on 24 Oct", same_instant(r.lock_at, at("2026-10-24T11:00:00+08:00")),
              f"got {r.lock_at.isoformat()}")
        return 0 if FAIL else 1
    finally:
        tmp.unlink(missing_ok=True)


async def main() -> int:
    await build_schema()
    await seed()
    set_draw()
    gr.get_grade_matches = fake_get_grade_matches
    playhq_client.get_seasons = fake_get_seasons
    playhq_client.get_teams = fake_get_teams

    if "--control" in sys.argv:
        return await run_control()

    print("1. Applecross (WA): first match 12:00 AWST on Sat 24 Oct, a later one at 13:30")
    fs = await season(APPLECROSS)
    await generate(fantasy_engine, fs.id)
    rs = await rounds_of(fs.id)
    check("two rounds from the draw", len(rs) == 2, f"got {len(rs)}")
    r1 = rs[0]
    check("round 1 locks 11:00 AWST on 24 Oct", same_instant(r1.lock_at, at("2026-10-24T11:00:00+08:00")), r1.lock_at.isoformat())
    check("the earliest of the day's matches is used, not the 13:30", first_start_of(r1) == "12:00", repr(first_start_of(r1)))
    check("round 2 locks 11:00 AWST on 31 Oct", same_instant(rs[1].lock_at, at("2026-10-31T11:00:00+08:00")), rs[1].lock_at.isoformat())

    print("2. Another state: a Victorian club in daylight time")
    fs2 = await season(MELB)
    await generate(fantasy_engine, fs2.id)
    r = (await rounds_of(fs2.id))[0]
    check("locks 11:00 AEDT (+11:00)", same_instant(r.lock_at, at("2026-10-24T11:00:00+11:00")), r.lock_at.isoformat())

    print("3. A draw with dates and no times falls back to 09:00 local")
    fs3 = await season(NOTIME)
    await generate(fantasy_engine, fs3.id)
    r = (await rounds_of(fs3.id))[0]
    check("09:00 in the club's own zone (AWST), not Melbourne", same_instant(r.lock_at, at("2026-10-24T09:00:00+08:00")), r.lock_at.isoformat())
    check("first_start stays empty", first_start_of(r) is None, repr(first_start_of(r)))

    print("4. A club with no state of its own uses its directory record")
    fs4 = await season(NOSTATE)
    await generate(fantasy_engine, fs4.id)
    r = (await rounds_of(fs4.id))[0]
    check("Western Australia -> Perth time", same_instant(r.lock_at, at("2026-10-24T11:00:00+08:00")), r.lock_at.isoformat())

    print("5. The season rule lock_timezone still wins")
    fs5 = await season(FORCED, {"lock_timezone": "Australia/Adelaide"})
    await generate(fantasy_engine, fs5.id)
    r = (await rounds_of(fs5.id))[0]
    check("11:00 Adelaide (+10:30)", same_instant(r.lock_at, at("2026-10-24T11:00:00+10:30")), r.lock_at.isoformat())

    print("6. The draw moves a match: the lock follows it")
    DRAW[GUID[APPLECROSS]] = [match("2026-10-24", "14:00:00", APPLECROSS), match("2026-10-31", "12:00:00", APPLECROSS)]
    await generate(fantasy_engine, fs.id)
    r1 = (await rounds_of(fs.id))[0]
    check("now 13:00 AWST", same_instant(r1.lock_at, at("2026-10-24T13:00:00+08:00")), r1.lock_at.isoformat())

    print("7. A Play-Cricket blip: the calendar returns nothing, a stored game keeps the round alive")
    async with Session() as s:
        sx = (await s.execute(select(Season).where(Season.organisation_id == APPLECROSS))).scalars().first()
        gx = (await s.execute(select(Grade).where(Grade.season_id == sx.id))).scalars().first()
        s.add(Game(id=uuid.uuid4(), grade_id=gx.id, played_at=date(2026, 10, 24), home_team="Applecross", away_team="Rovers",
                   home_org_id=APPLECROSS, status="COMPLETED"))
        await s.commit()
    saved = DRAW[GUID[APPLECROSS]]
    DRAW[GUID[APPLECROSS]] = []
    await generate(fantasy_engine, fs.id)
    r1 = (await rounds_of(fs.id))[0]
    check("the round survives on the stored game", r1.start_date == date(2026, 10, 24), repr(r1.start_date))
    check("lock unchanged by an empty draw", same_instant(r1.lock_at, at("2026-10-24T13:00:00+08:00")), r1.lock_at.isoformat())
    check("start unchanged by an empty draw", first_start_of(r1) == "14:00", repr(first_start_of(r1)))
    DRAW[GUID[APPLECROSS]] = saved

    print("8. A time an admin set by hand is kept; Use the default goes back to one hour before the match")
    DRAW[GUID[APPLECROSS]] = [match("2026-10-24", "12:00:00", APPLECROSS), match("2026-10-31", "12:00:00", APPLECROSS)]
    await generate(fantasy_engine, fs.id)
    club = SimpleNamespace(id=APPLECROSS)
    r1 = (await rounds_of(fs.id))[0]
    manual = datetime(2026, 10, 23, 20, 0, tzinfo=timezone(timedelta(hours=8)))
    async with Session() as s:
        await fantasy_router.set_round_lock(str(r1.id), fantasy_router.RoundLock(lock_at=manual.isoformat()), club=club, db=s, _=None)
    await generate(fantasy_engine, fs.id)
    r1 = (await rounds_of(fs.id))[0]
    check("hand-set lock survives the refresh", r1.lock_manual and same_instant(r1.lock_at, manual), r1.lock_at.isoformat())
    async with Session() as s:
        listing = await fantasy_router.list_rounds(str(fs.id), club=club, db=s, _=None)
    row = next(x for x in listing["rounds"] if x["round_number"] == 1)
    check("the Locks column offers 11:00 AWST as the default", same_instant(at(row["default_lock_at"]), at("2026-10-24T11:00:00+08:00")), row["default_lock_at"])
    async with Session() as s:
        await fantasy_router.set_round_lock(str(r1.id), fantasy_router.RoundLock(lock_at=None), club=club, db=s, _=None)
    r1 = (await rounds_of(fs.id))[0]
    check("Use the default lands on 11:00 AWST", (not r1.lock_manual) and same_instant(r1.lock_at, at("2026-10-24T11:00:00+08:00")), r1.lock_at.isoformat())

    print(f"\n{PASS} passed, {FAIL} failed")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
