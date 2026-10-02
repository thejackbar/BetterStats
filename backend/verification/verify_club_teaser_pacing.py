"""The paced club teaser crawl (services/call_pacer.py, club_teaser.run_forever).

Runs the SHIPPED pacer, window logic, crawl cycle and loop against a real
Postgres, with a scripted stand-in for Cricket Australia so no live call is
made. It checks the three things the crawl exists for:

  * the calls go out at the rate the operator set, as a steady trickle with no
    bursts (the pacer, and then a real crawl measured end to end),
  * it only crawls inside its hours (Perth) and only while it is switched on
    and not stopped,
  * a bad day cannot turn it into a hot loop.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_pacing.py
"""
from __future__ import annotations

import asyncio
import math
import os
import random
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

# A control run against the previous commit must REPORT the feature missing
# rather than die on an ImportError before a single check runs.
MISSING: list[str] = []
try:
    from app.services import club_teaser as ct
    from app.services.call_pacer import CallPacer
    from app.services.club_teaser_ddl import STATEMENTS, DOWNGRADE
    from app.services import platform_settings as ps
    for name in ("paced_cycle", "run_forever", "in_window", "seconds_until_open", "PacedConfig", "PERTH"):
        if not hasattr(ct, name):
            MISSING.append(f"club_teaser.{name} is missing")
    if not hasattr(ps, "get_club_teaser_rate"):
        MISSING.append("platform_settings.get_club_teaser_rate is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ct = CallPacer = STATEMENTS = DOWNGRADE = ps = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]

# THESE SUITES ARE DESTRUCTIVE. They create tables, delete from marketing_clubs,
# drop club_teaser_snapshots and reset platform_settings. Refuse anything that
# is not plainly a throwaway verification database, so a mistyped
# DATABASE_URL (or running inside the app container without overriding it)
# cannot reach real data.
_db_name = make_url(DB).database or ""
if "verify" not in _db_name.lower():
    print(f"REFUSING to run: database {_db_name!r} is not a verification database "
          "(its name must contain 'verify'). These checks delete and drop tables.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []
ROOT = Path(__file__).resolve().parent.parent


def check(label: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(label)
        print(f"  FAIL {label}{('  -- ' + detail) if detail else ''}")


def g() -> str:
    return str(uuid.uuid4())


async def raises(coro_fn, exc=ValueError) -> bool:
    try:
        r = coro_fn()
        if asyncio.iscoroutine(r):
            await r
    except exc:
        return True
    except Exception:  # noqa: BLE001
        return False
    return False


# --------------------------------------------------------------------------
# The stand-in for Cricket Australia, at the level LiveAPI calls it (the two
# client modules), so the REAL LiveAPI and its pacer are what get exercised.
# One club costs exactly CALLS_PER_CLUB calls: resolve, seasons, the probe,
# teams, batting + bowling + fielding, one ladder.
# --------------------------------------------------------------------------
CALLS_PER_CLUB = 8
DIR: dict[str, str] = {}      # club name -> the directory's own guid


def bat_row(pid, name, runs):
    return {"id": pid, "name": name, "statistics": {
        "battingAggregate": runs, "battingInnings": 10, "battingNotOuts": 1,
        "battingHighScore": 80, "isBattingHSNotOut": False, "batting50s": 2, "batting100s": 0}}


class StubPH:
    @staticmethod
    async def search_organisations(q):
        return [{"name": q, "organisationGuid": "ca-" + DIR[q], "playHQId": DIR[q]}]

    @staticmethod
    async def get_seasons(org):
        return [{"id": "S1", "name": "Summer 2025/26", "startDate": "2025-10-01"}]

    @staticmethod
    async def get_teams(org, season):
        return [{"id": "T1", "grades": [{"id": "G1", "name": "A Grade"}]}]

    @staticmethod
    async def get_batting_stats(org, season, grade=None):
        return [bat_row("p1", "John Smith", 432)]

    @staticmethod
    async def get_bowling_stats(org, season, grade=None):
        return []

    @staticmethod
    async def get_fielding_stats(org, season, grade=None):
        return []


class BoomPH(StubPH):
    @staticmethod
    async def get_seasons(org):
        raise RuntimeError("upstream exploded")


class StubGR:
    @staticmethod
    async def get_grade_ladder(grade):
        return None


class SpyPacer(CallPacer if CallPacer else object):
    """A real pacer that also records when each call was actually let go."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.went: list[float] = []
        self.reserved = 0

    def reserve(self):
        self.reserved += 1
        return super().reserve()

    async def wait(self):
        await super().wait()
        self.went.append(time.monotonic())


def live_factory(pacer, ph=StubPH):
    def make():
        api = ct.LiveAPI(pacer=pacer)
        api._ph, api._gr = ph, StubGR
        return api
    return make


# --------------------------------------------------------------------------
# Time, in Perth
# --------------------------------------------------------------------------
def perth(h, m=0, s=0, day=30):
    return datetime(2026, 9, day, h, m, s, tzinfo=ct.PERTH)


async def reset(s=None):
    async with Session() as s_:
        await s_.execute(text("DELETE FROM club_teaser_snapshots"))
        await s_.execute(text("DELETE FROM marketing_clubs"))
        await s_.commit()


async def mk_clubs(n, prefix="Pace"):
    out = []
    async with Session() as s_:
        for i in range(n):
            name, guid = f"{prefix} Club {i:02d} CC", g()
            DIR[name] = guid
            await s_.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded,
                not_interested, trial_modules, status, source)
                VALUES (CAST(:id AS uuid), :guid, :name, 'club', false, false, '[]'::jsonb, 'new', 'grassroots_api')"""),
                {"id": g(), "guid": guid, "name": name})
            out.append(name)
        await s_.commit()
    return out


async def snapshot_count():
    async with Session() as s_:
        return await s_.scalar(text("SELECT count(*) FROM club_teaser_snapshots"))


def cfg(rate=3.0, start=5, end=22, modes=None):
    async def fn():
        return ct.PacedConfig(rate, start, end, {} if modes is None else modes)
    return fn


async def never_paused(_s):
    return False


async def main() -> None:
    if MISSING:
        check("the paced crawl is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    # ======================================================================
    # 1. The pacer's arithmetic (no waiting: clock and random are injected)
    # ======================================================================
    print("pacer")
    t = {"now": 0.0}
    clk = lambda: t["now"]  # noqa: E731
    p = CallPacer(2.0, jitter=0.25, clock=clk, rng=lambda: 0.5)
    seq = [p.reserve() for _ in range(4)]
    check("with no jitter offset the slots are exactly one gap apart (2 a second = 0.5s)",
          seq == [0.0, 0.5, 1.0, 1.5], str(seq))
    p0 = CallPacer(4.0, jitter=0.0, clock=clk)
    check("jitter 0 is a metronome", [p0.reserve() for _ in range(3)] == [0.0, 0.25, 0.5])

    rnd = random.Random(7)
    pj = CallPacer(3.0, jitter=0.25, clock=clk, rng=rnd.random)
    at = [pj.reserve() for _ in range(20001)]
    gaps = [b - a for a, b in zip(at, at[1:])]
    check("over 20,000 calls the average rate is the one asked for (3 a second) to within 1%",
          abs((len(gaps) / sum(gaps)) - 3.0) / 3.0 < 0.01, f"{len(gaps) / sum(gaps):.4f}")
    check("no gap is shorter than (1 - jitter) / rate or longer than (1 + jitter) / rate",
          min(gaps) >= 0.75 / 3.0 - 1e-9 and max(gaps) <= 1.25 / 3.0 + 1e-9, f"{min(gaps)} {max(gaps)}")
    mean = sum(gaps) / len(gaps)
    sd = math.sqrt(sum((x - mean) ** 2 for x in gaps) / len(gaps))
    check("the gaps genuinely vary, so the load wobbles instead of ticking", sd > 0.02, f"sd {sd:.4f}")
    check("and the wobble is centred, not one-sided (mean gap within 1% of 1/rate)",
          abs(mean - 1 / 3.0) / (1 / 3.0) < 0.01, f"{mean}")

    t["now"] = 0.0
    pi = CallPacer(2.0, jitter=0.0, clock=clk)
    for _ in range(3):
        pi.reserve()
    t["now"] = 3600.0                                  # an hour of silence
    after = [pi.reserve() for _ in range(5)]
    check("an hour idle is NOT banked: the first call goes at once, the rest are spaced again",
          after[0] == 0.0 and all(b - a > 0.4 for a, b in zip(after, after[1:])), str(after))
    check("so the calls after a quiet spell are not a burst (5 calls span at least 2 seconds)",
          after[-1] - after[0] >= 1.99, str(after))

    t["now"] = 10.0
    pc = CallPacer(1.0, jitter=0.0, clock=clk)
    slots = [pc.reserve() for _ in range(50)]          # 50 "tasks" reserving in the same instant
    check("fifty callers in the same instant get fifty different slots, one gap apart",
          len(set(slots)) == 50 and all(abs((b - a) - 1.0) < 1e-9 for a, b in zip(slots, slots[1:])))
    pr = CallPacer(1.0, jitter=0.0, clock=clk)
    pr.reserve(); pr.reserve()
    pr.set_rate(4.0)
    check("a rate change is picked up from the next reservation",
          pr.rate == 4.0 and abs((lambda a, b: b - a)(pr.reserve(), pr.reserve()) - 0.25) < 1e-9)
    bad = []
    for r in (0, -1, float("nan"), float("inf"), "fast", None, True is False):
        try:
            CallPacer(r)
            bad.append(r)
        except (ValueError, TypeError):
            pass
    check("a zero, negative, non-finite or non-numeric rate is refused", not bad, str(bad))
    check("a jitter outside [0, 1) is refused", all([await raises(lambda j=j: CallPacer(1.0, jitter=j)) for j in (-0.1, 1.0, 2)]))

    # real waiting: 100 concurrent tasks share ONE budget
    real = CallPacer(200.0)
    started = time.monotonic()
    await asyncio.gather(*[real.wait() for _ in range(100)])
    took = time.monotonic() - started
    check("100 concurrent waiters finish in about 99 gaps (0.5s at 200 a second), not at once",
          0.35 < took < 0.9, f"{took:.3f}s")

    # ======================================================================
    # 2. The hours (Perth)
    # ======================================================================
    print("window")
    check("05:00:00 Perth is in and 04:59:59 is out",
          ct.in_window(perth(5), 5, 22) and not ct.in_window(perth(4, 59, 59), 5, 22))
    check("21:59:59 is in and 22:00:00 is out",
          ct.in_window(perth(21, 59, 59), 5, 22) and not ct.in_window(perth(22), 5, 22))
    check("the hours are Perth's, whatever zone the clock is in (21:00 UTC is 05:00 next day in Perth)",
          ct.in_window(datetime(2026, 9, 29, 21, 0, tzinfo=timezone.utc), 5, 22)
          and not ct.in_window(datetime(2026, 9, 29, 20, 59, tzinfo=timezone.utc), 5, 22))
    check("an end of 24 runs to midnight", ct.in_window(perth(23, 59), 5, 24) and not ct.in_window(perth(0, 30), 5, 24))
    check("inside the hours there is no wait", ct.seconds_until_open(perth(12), 5, 22) == 0.0)
    check("at 04:00 it is an hour to opening", ct.seconds_until_open(perth(4), 5, 22) == 3600.0)
    check("at 22:30 it is 6.5 hours to tomorrow's 05:00",
          ct.seconds_until_open(perth(22, 30), 5, 22) == 6.5 * 3600, str(ct.seconds_until_open(perth(22, 30), 5, 22)))

    # ======================================================================
    # 3. The settings (real Postgres)
    # ======================================================================
    print("settings")
    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
        # Lifespan DDL (main.py), not on the ORM model: the shared "not played" predicate reads it.
        await c.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS innings_totals JSONB"))
        for s in DOWNGRADE:
            await c.execute(text(s))
    async with engine.begin() as c:
        for s in STATEMENTS:
            await c.execute(text(s))
        await c.execute(text("""CREATE TABLE IF NOT EXISTS platform_settings (
            id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1), settings JSONB NOT NULL DEFAULT '{}',
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))
        await c.execute(text("INSERT INTO platform_settings (id, settings) VALUES (1, '{}') "
                             "ON CONFLICT (id) DO UPDATE SET settings = '{}'"))
    async with Session() as s_:
        check("unset, the crawl is OFF (rate 0)", await ps.get_club_teaser_rate(s_) == 0.0)
        check("unset, the hours are 05:00 to 22:00", await ps.get_club_teaser_window(s_) == (5, 22))
        await ps.update_settings(s_, {"club_teaser_calls_per_second": 3})
        check("a rate is stored and read back as a float", await ps.get_club_teaser_rate(s_) == 3.0)
        await ps.update_settings(s_, {"club_teaser_calls_per_second": 1.25})
        check("fractions are allowed (1.25 a second)", await ps.get_club_teaser_rate(s_) == 1.25)
        for label, val in (("zero", 0), ("negative", -1), ("below the floor", 0.01), ("above the ceiling", 11),
                           ("text", "fast"), ("not-a-number", float("nan")), ("infinity", float("inf")), ("a bool", True)):
            check(f"a rate that is {label} is refused",
                  await raises(lambda v=val: ps.update_settings(s_, {"club_teaser_calls_per_second": v})))
        check("a refused rate leaves the stored one alone", await ps.get_club_teaser_rate(s_) == 1.25)
        await ps.update_settings(s_, {"club_teaser_calls_per_second": None})
        check("null clears it back to off", await ps.get_club_teaser_rate(s_) == 0.0)
        await ps.update_settings(s_, {"club_teaser_window_start": 0, "club_teaser_window_end": 24})
        check("the whole day is expressible (0 to 24)", await ps.get_club_teaser_window(s_) == (0, 24))
        await ps.update_settings(s_, {"club_teaser_window_start": 6, "club_teaser_window_end": 20})
        check("a custom window is read back", await ps.get_club_teaser_window(s_) == (6, 20))
        for label, patch in (("an end of 0", {"club_teaser_window_end": 0}), ("a start of 24", {"club_teaser_window_start": 24}),
                             ("half an hour", {"club_teaser_window_start": 5.5}), ("a bool hour", {"club_teaser_window_end": True}),
                             ("a start after the end", {"club_teaser_window_start": 21}),
                             ("a start equal to the end", {"club_teaser_window_start": 20})):
            check(f"{label} is refused", await raises(lambda p_=patch: ps.update_settings(s_, p_)))
        check("a refused window leaves the stored one alone", await ps.get_club_teaser_window(s_) == (6, 20))
        await s_.execute(text("UPDATE platform_settings SET settings = "
                              "'{\"club_teaser_calls_per_second\": 99, \"club_teaser_window_start\": 22, \"club_teaser_window_end\": 5}'"))
        await s_.commit()
        check("a stored rate above the ceiling reads as OFF rather than being clamped up into traffic",
              await ps.get_club_teaser_rate(s_) == 0.0)
        check("a stored window that is backwards reads as the default rather than a window that never opens",
              await ps.get_club_teaser_window(s_) == (5, 22))
        await s_.execute(text("UPDATE platform_settings SET settings = '{}'")); await s_.commit()

        # the General Settings route bodies carry the three keys
        from app.routers import club_admin as ca
        from fastapi import HTTPException
        body = ca.GeneralSettingsUpdate(club_teaser_calls_per_second=2.5, club_teaser_window_start=6,
                                        club_teaser_window_end=21)
        out = await ca.patch_general_settings(body=body, _=None, db=s_)
        check("the General Settings PATCH sets the rate and hours and returns them",
              out["club_teaser_calls_per_second"] == 2.5 and out["club_teaser_window_start"] == 6
              and out["club_teaser_window_end"] == 21, str({k: v for k, v in out.items() if "teaser" in k}))
        got = await ca.get_general_settings(_=None, db=s_)
        check("and the GET reads them back", got["club_teaser_calls_per_second"] == 2.5
              and got["club_teaser_window_start"] == 6)
        try:
            await ca.patch_general_settings(body=ca.GeneralSettingsUpdate(club_teaser_calls_per_second=50), _=None, db=s_)
            refused = False
        except HTTPException as e:
            refused = e.status_code == 422
        check("a bad rate over the API is a 422, not a stored value", refused)
        loaded = await ct.load_config(Session)
        check("the crawl reads its rate, hours and type filters from those settings",
              (loaded.rate, loaded.start_hour, loaded.end_hour) == (2.5, 6, 21)
              and loaded.type_modes == ct.DEFAULT_TYPE_MODES, str(loaded))
        await s_.execute(text("UPDATE platform_settings SET settings = '{}'")); await s_.commit()

    # ======================================================================
    # 4. One crawl cycle (real Postgres, scripted CA)
    # ======================================================================
    print("cycle")
    await reset()
    await mk_clubs(3)
    pacer = SpyPacer(500.0)
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=0), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer))
    check("rate 0 is OFF: nothing pulled, nothing reserved, a short wait to re-read the settings",
          out["status"] == "off" and out["wait"] == ct.OFF_SECONDS and await snapshot_count() == 0
          and pacer.reserved == 0, str(out))
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(), is_paused=never_paused,
                               now_fn=lambda: perth(23), api_factory=live_factory(pacer))
    check("at 23:00 it is outside the hours: nothing pulled, and it waits no longer than the poll interval",
          out["status"] == "outside_window" and await snapshot_count() == 0 and pacer.reserved == 0
          and 1 <= out["wait"] <= ct.OUTSIDE_POLL_SECONDS, str(out))
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(), is_paused=never_paused,
                               now_fn=lambda: perth(4, 59, 30), api_factory=live_factory(pacer))
    check("30 seconds before opening it waits about 30 seconds, not the whole poll interval",
          out["status"] == "outside_window" and 29 <= out["wait"] <= 31, str(out))

    async def paused(_s):
        return True
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(), is_paused=paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer))
    check("the operator's Stop switch is honoured before anything is pulled",
          out["status"] == "stopped" and await snapshot_count() == 0 and pacer.reserved == 0, str(out))

    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=500), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer))
    check("in the hours, on, and not stopped it pulls what is due and asks for no wait (it is continuous)",
          out["status"] == "worked" and out["wait"] == 0 and out["summary"]["ok"] == 3
          and await snapshot_count() == 3, str(out))
    check("every call the clubs made went through the shared pacer (3 clubs x 8 calls)",
          out["summary"]["calls"] == 3 * CALLS_PER_CLUB and pacer.reserved == 3 * CALLS_PER_CLUB,
          f"{out['summary']['calls']} calls, {pacer.reserved} slots")
    check("the pacer was set to the configured rate", pacer.rate == 500.0)
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=250), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer))
    check("nothing left due is IDLE, with a five minute wait, and a changed rate is picked up",
          out["status"] == "idle" and out["wait"] == ct.IDLE_SECONDS and pacer.rate == 250.0, str(out))

    # a batch is bounded, so a settings change lands within a cycle
    await reset()
    await mk_clubs(12)
    pacer = SpyPacer(2000.0)
    kw = dict(session_maker=Session, config_fn=cfg(rate=2000), is_paused=never_paused,
              now_fn=lambda: perth(10), api_factory=live_factory(pacer), batch=5)
    a = await ct.paced_cycle(pacer, **kw)
    b = await ct.paced_cycle(pacer, **kw)
    c_ = await ct.paced_cycle(pacer, **kw)
    d = await ct.paced_cycle(pacer, **kw)
    check("twelve due clubs take cycles of 5, 5 and 2, then it is idle",
          [x["summary"]["due"] for x in (a, b, c_, d)] == [5, 5, 2, 0]
          and [x["status"] for x in (a, b, c_, d)] == ["worked", "worked", "worked", "idle"], str([a, b, c_, d]))
    check("and no club was pulled twice", await snapshot_count() == 12)

    # the hours close part way through a batch
    await reset()
    await mk_clubs(6)
    pacer = SpyPacer(2000.0)
    clock = {"t": perth(21, 59, 50)}
    made = {"n": 0}

    def closing_factory():
        made["n"] += 1
        if made["n"] == 2:
            clock["t"] = perth(22, 0, 5)          # the hours end while club 2 is being pulled
        return live_factory(pacer)()
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=2000), is_paused=never_paused,
                               now_fn=lambda: clock["t"], api_factory=closing_factory, batch=6, club_concurrency=1)
    check("when the hours end mid-batch it stops BETWEEN clubs: the club in flight finishes, no new one starts",
          out["status"] == "outside_window" and out["summary"]["stopped"] and out["summary"]["ok"] == 2
          and await snapshot_count() == 2, str(out))
    check("and it then waits for the hours to reopen, not the idle interval",
          1 <= out["wait"] <= ct.OUTSIDE_POLL_SECONDS)

    # the Stop switch part way through
    await reset()
    await mk_clubs(6)
    asked = {"n": 0}

    async def stop_late(_s):
        asked["n"] += 1
        return asked["n"] > 3                      # pre-check + two clubs, then Stop
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=2000), is_paused=stop_late,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer), batch=6, club_concurrency=1)
    check("Stop pressed mid-batch halts it between clubs and reports 'stopped'",
          out["status"] == "stopped" and out["summary"]["ok"] == 2 and await snapshot_count() == 2, str(out))

    # a bad day
    await reset()
    await mk_clubs(4)
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=2000), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(pacer, BoomPH), batch=4)
    check("a whole cycle of errors is 'trouble': it backs off a quarter of an hour instead of hammering on",
          out["status"] == "trouble" and out["wait"] == ct.TROUBLE_SECONDS and out["summary"]["error"] == 4, str(out))
    async with Session() as s_:
        due_now = await ct.due_clubs(s_, 100)
    check("and those clubs are backed off, so the next cycle does not pick the same four again",
          not due_now, str([c["name"] for c in due_now]))
    await reset()
    await mk_clubs(4)
    flip = {"n": 0}

    def half_bad():
        flip["n"] += 1
        return live_factory(pacer, BoomPH if flip["n"] == 1 else StubPH)()
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=2000), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=half_bad, batch=4, club_concurrency=1)
    check("one bad club among good ones is just 'worked'", out["status"] == "worked"
          and out["summary"]["error"] == 1 and out["summary"]["ok"] == 3, str(out))

    # who is eligible follows the configured Directory type filters
    await reset()
    await mk_clubs(1, "Plain")
    await mk_clubs(1, "Northside Junior")
    out = await ct.paced_cycle(pacer, session_maker=Session, config_fn=cfg(rate=2000, modes={"junior": "exclude"}),
                               is_paused=never_paused, now_fn=lambda: perth(10),
                               api_factory=live_factory(pacer), batch=10)
    async with Session() as s_:
        pulled = [r[0] for r in (await s_.execute(text(
            "SELECT mc.name FROM club_teaser_snapshots t JOIN marketing_clubs mc ON mc.id = t.marketing_club_id"))).all()]
    check("the configured type filters decide who is pulled (the junior club is left out)",
          pulled == ["Plain Club 00 CC"] and out["summary"]["due"] == 1, str(pulled))

    # ======================================================================
    # 5. The rate, measured on a real crawl
    # ======================================================================
    print("measured")
    await reset()
    await mk_clubs(10)
    RATE = 60.0
    spy = SpyPacer(RATE)
    started = time.monotonic()
    out = await ct.paced_cycle(spy, session_maker=Session, config_fn=cfg(rate=RATE), is_paused=never_paused,
                               now_fn=lambda: perth(10), api_factory=live_factory(spy), batch=10, club_concurrency=2)
    elapsed = time.monotonic() - started
    calls = out["summary"]["calls"]
    went = spy.went
    check("10 clubs at 8 calls each went out as 80 paced calls", calls == 80 and len(went) == 80, f"{calls} {len(went)}")
    # An unpaced crawl records nothing here; that must FAIL these checks, not
    # crash the run (a control run that crashes is not a control run).
    span = (went[-1] - went[0]) if len(went) > 1 else 0.0
    measured = (len(went) - 1) / span if span > 0 else (float("inf") if len(went) > 1 else 0.0)
    check(f"the calls left at the set rate ({RATE:g} a second), not faster (measured {measured:.1f})",
          measured <= RATE * 1.12, f"{measured:.1f}/s over {span:.2f}s")
    check(f"and not much slower either, so the crawl does finish (measured {measured:.1f})",
          measured >= RATE * 0.75, f"{measured:.1f}/s")
    worst = 0
    for i, t0 in enumerate(went):
        worst = max(worst, sum(1 for x in went[i:] if x < t0 + 0.5))
    check(f"no half second holds a burst: at most {int(RATE * 0.5 * 1.25)} calls in any 0.5s (worst {worst})",
          worst <= RATE * 0.5 * 1.25, str(worst))
    check("two clubs at a time still share ONE rate (that is the point of a shared pacer)",
          elapsed > 80 / RATE * 0.9, f"{elapsed:.2f}s for 80 calls")

    # ======================================================================
    # 6. The loop
    # ======================================================================
    print("loop")
    state = {"rate": 0.0, "start": 5, "end": 22}

    async def live_cfg():
        return ct.PacedConfig(state["rate"], state["start"], state["end"], {})
    sleeps: list[float] = []

    async def fake_sleep(s_):
        sleeps.append(s_)
    await reset()
    clockL = {"t": perth(10)}
    poke = {"n": 0}

    async def cfg_walk():
        poke["n"] += 1
        if poke["n"] == 3:
            raise RuntimeError("settings read blew up")
        return await live_cfg()

    await ct.run_forever(pacer=SpyPacer(2000.0), session_maker=Session, config_fn=cfg_walk, is_paused=never_paused,
                         now_fn=lambda: clockL["t"], sleep=fake_sleep, api_factory=live_factory(SpyPacer(2000.0)),
                         max_cycles=2)
    check("switched off, the loop sleeps the short settings poll, twice, and does no work",
          sleeps == [ct.OFF_SECONDS, ct.OFF_SECONDS] and await snapshot_count() == 0, str(sleeps))

    sleeps.clear()
    state["rate"] = 2000.0
    await ct.run_forever(pacer=SpyPacer(2000.0), session_maker=Session, config_fn=cfg_walk, is_paused=never_paused,
                         now_fn=lambda: clockL["t"], sleep=fake_sleep, api_factory=live_factory(SpyPacer(2000.0)),
                         max_cycles=2)
    check("a cycle that raises is logged and followed by a pause, never a hot loop, and the loop carries on",
          sleeps[0] == ct.ERROR_SECONDS and len(sleeps) == 2, str(sleeps))

    sleeps.clear()
    await reset()
    await mk_clubs(7)
    sp = SpyPacer(2000.0)
    await ct.run_forever(pacer=sp, session_maker=Session, config_fn=live_cfg, is_paused=never_paused,
                         now_fn=lambda: clockL["t"], sleep=fake_sleep, api_factory=live_factory(sp),
                         batch=3, max_cycles=4)
    check("while there is work it never sleeps between cycles (3 + 3 + 1 clubs), then idles",
          sleeps == [ct.IDLE_SECONDS] and await snapshot_count() == 7, f"{sleeps} {await snapshot_count()}")

    sleeps.clear()
    clockL["t"] = perth(23)
    await ct.run_forever(pacer=sp, session_maker=Session, config_fn=live_cfg, is_paused=never_paused,
                         now_fn=lambda: clockL["t"], sleep=fake_sleep, api_factory=live_factory(sp), max_cycles=1)
    check("outside the hours the loop sleeps toward opening, capped so a widened window is noticed",
          sleeps == [ct.OUTSIDE_POLL_SECONDS], str(sleeps))

    task = asyncio.create_task(ct.run_forever(pacer=sp, session_maker=Session, config_fn=live_cfg,
                                              is_paused=never_paused, now_fn=lambda: perth(23)))
    await asyncio.sleep(0.2)
    task.cancel()
    try:
        await task
        cancelled = False
    except asyncio.CancelledError:
        cancelled = True
    check("cancelling the task (app shutdown) ends the loop promptly", cancelled and task.done())

    # ======================================================================
    # 7. Wiring
    # ======================================================================
    print("wiring")
    main_src = (ROOT / "app/main.py").read_text()
    sched_src = (ROOT / "app/jobs/scheduler.py").read_text()
    ct_src = Path(ct.__file__).read_text()
    check("the app starts the crawl at boot and HOLDS the task (a bare create_task can be collected)",
          "club_teaser.run_forever()" in main_src or "_club_teaser.run_forever()" in main_src)
    i = main_src.index("run_forever()")
    check("the started task is kept in _BACKGROUND_TASKS", "_BACKGROUND_TASKS.add(_teaser_task)" in main_src[i:i + 400])
    check("and is cancelled at shutdown", "_teaser_task.cancel()" in main_src)
    check("a failure to start it is logged and never blocks boot", "could not start the club teaser crawl" in main_src)
    check("the burst-and-rest cron job is gone from the scheduler",
          "pull_club_teasers" not in sched_src and "nightly_club_teasers" not in sched_src
          and "OrTrigger" not in sched_src)
    check("LiveAPI takes a pacer and waits on it before every call",
          "pacer=None" in ct_src and "await self._pacer.wait()" in ct_src)
    check("the crawl asks the Stop switch and the hours between clubs", "should_stop=guard" in ct_src
          and "in_window(now_fn()" in ct_src and "is_crawl_paused" in ct_src)
    pacer_src = (ROOT / "app/services/call_pacer.py").read_text()
    check("the pacer imports nothing from the app or the database (it is checked without either)",
          "from app" not in pacer_src and "import app" not in pacer_src and "sqlalchemy" not in pacer_src)
    script = (ROOT / "app/scripts/pull_club_teasers.py").read_text()
    check("the by-hand script can pace itself (--rate) with the same pacer",
          '"--rate"' in script and "CallPacer(a.rate)" in script and "LiveAPI(pacer=pacer)" in script)
    check("the script refuses an out-of-range rate before pulling anything",
          "TEASER_MAX_RATE" in script and "ap.error" in script)

    async with engine.begin() as c:
        for s in DOWNGRADE:
            await c.execute(text(s))
        # platform_settings is left in place: the suites share one database and
        # others create it IF NOT EXISTS. Only the settings row is reset.
        await c.execute(text("UPDATE platform_settings SET settings = '{}'"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


asyncio.run(main())
