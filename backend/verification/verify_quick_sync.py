"""Quick Sync: the last seven days of fixtures, on demand.

The button on /admin/sync. It rides the incremental path the scheduled sync
already uses (``sync_organisation(..., since=)``), so what is checked here is
the wiring and the one trap that could do real damage: the watermark.

A scheduled run asks "what happened since this club's last sync". If a Quick
Sync, which only looks seven days back, counted as that last sync, then a club
that had been silent for a month and then pressed Quick Sync would have the
month in between hidden from every later scheduled run. So it carries its own
kind, ``org_quick``, outside the watermark kinds.

What is checked, through the SHIPPED route body and services:

  · the route starts a run of kind ``org_quick`` and hands ``_sync_safe`` a
    ``since`` exactly QUICK_LOOKBACK_DAYS before today
  · a second click while one is in flight answers ``already_running`` and
    starts nothing
  · ``_sync_safe`` forwards ``since`` to ``sync_organisation`` (and a plain
    Sync Now still passes none, so it stays a whole-history sync)
  · against a real Postgres: a successful quick run does NOT move the
    watermark ``plan_run`` computes (control: an ``org_recent`` run at the same
    moment DOES, which proves the check can fail)
  · a quick run is not read as "history pulled" by the full-kind tuple

Run:  DATABASE_URL=... python -m verification.verify_quick_sync
"""
import asyncio
import os
import sys
import uuid
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

DB = os.environ.get(
    "DATABASE_URL",
    "postgresql+asyncpg://postgres@/betterstats_verify?host=/var/run/pgsock&port=5439",
)

PASS = FAIL = 0


def ck(name, cond, extra=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS {name}")
    else:
        FAIL += 1
        print(f"FAIL {name} {extra}")


class _Bg:
    """Stands in for BackgroundTasks: records the task instead of running it."""
    def __init__(self):
        self.tasks = []

    def add_task(self, fn, *a, **kw):
        self.tasks.append((fn, a, kw))


class _User:
    id = uuid.uuid4()


async def main():
    from app.routers import organisations as orgs
    from app.services import auto_sync, sync as sync_mod

    org_id = uuid.uuid4()
    engine = create_async_engine(DB)
    maker = async_sessionmaker(engine, expire_on_commit=False)

    async with maker() as s:
        await s.execute(text(
            "INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Quick Sync CC', true)"),
            {"i": org_id})
        await s.commit()

    # ---- the route body (run recording and the background task are stubbed;
    # ---- everything the route itself decides is real) -----------------------
    started = []

    async def fake_start_sync_run(org, kind, **kw):
        started.append((org, kind, kw))
        return uuid.uuid4()

    real_start = sync_mod.start_sync_run
    sync_mod.start_sync_run = fake_start_sync_run
    try:
        orgs._org_sync_running.discard(str(org_id))
        bg = _Bg()
        res = await orgs.trigger_quick_sync(str(org_id), bg, _User())
        today = datetime.now(timezone.utc).date()
        ck("route reports sync_started", res.get("status") == "sync_started", str(res))
        ck("route starts a run of kind org_quick",
           len(started) == 1 and started[0][1] == "org_quick", str(started))
        ck("run records who clicked", started and started[0][2].get("triggered_by_user_id") == _User.id)
        ck("response carries the window start",
           res.get("since") == (today - timedelta(days=7)).isoformat(), str(res.get("since")))
        fn, a, kw = bg.tasks[0] if bg.tasks else (None, (), {})
        ck("background task is _sync_safe", fn is orgs._sync_safe)
        ck("task is handed since = today - 7 days",
           bool(a) and a[-1] == today - timedelta(days=7), str(a))
        ck("task carries the org_quick kind", "org_quick" in a, str(a))
        ck("org is marked running", str(org_id) in orgs._org_sync_running)

        res2 = await orgs.trigger_quick_sync(str(org_id), _Bg(), _User())
        ck("second click answers already_running", res2.get("status") == "already_running", str(res2))
        ck("second click starts no new run", len(started) == 1)
    finally:
        sync_mod.start_sync_run = real_start
        orgs._org_sync_running.discard(str(org_id))

    # ---- _sync_safe forwards since -------------------------------------------
    seen = []

    async def fake_sync_organisation(oid, run_id=None, kind="org_full", since=None):
        seen.append({"kind": kind, "since": since})
        return {"games_new": 0}

    async def fake_finish(run_id, stats, error=None):
        return None

    real_sync, real_finish = orgs.sync_organisation, sync_mod.finish_sync_run
    orgs.sync_organisation = fake_sync_organisation
    sync_mod.finish_sync_run = fake_finish
    try:
        want = date(2026, 9, 26)
        await orgs._sync_safe(str(org_id), uuid.uuid4(), "org_quick", False, want)
        ck("_sync_safe forwards since to sync_organisation",
           seen and seen[-1] == {"kind": "org_quick", "since": want}, str(seen))
        await orgs._sync_safe(str(org_id), uuid.uuid4(), "org_full")
        ck("Sync Now still passes no since (whole history)",
           seen[-1] == {"kind": "org_full", "since": None}, str(seen[-1]))
    finally:
        orgs.sync_organisation, sync_mod.finish_sync_run = real_sync, real_finish
        orgs._org_sync_running.discard(str(org_id))

    # ---- the watermark, against the real plan_run and real Postgres ----------
    now = datetime.now(timezone.utc)

    async def add_run(kind, completed_ago_days, status="success"):
        async with maker() as s:
            await s.execute(text(
                "INSERT INTO sync_runs (id, org_id, kind, status, started_at, completed_at, stats) "
                "VALUES (:id, :o, :k, :st, :t, :t, '{}'::json)"),
                {"id": uuid.uuid4(), "o": org_id, "k": kind, "st": status,
                 "t": now - timedelta(days=completed_ago_days)})
            await s.commit()

    async def plan():
        async with maker() as s:
            return await auto_sync.plan_run(s, org_id, now)

    await add_run("org_full", 30)
    before = await plan()
    ck("baseline: a month since the last real sync, plan is recent",
       before["mode"] == "recent", str(before))
    ck("baseline: window reaches back past the month",
       before["since"] <= (now - timedelta(days=30)).date(), str(before["since"]))

    await add_run("org_quick", 0)
    after_quick = await plan()
    ck("a successful quick run does NOT move the watermark",
       after_quick["since"] == before["since"], f"{before['since']} -> {after_quick['since']}")
    ck("quick kind is not a watermark kind", "org_quick" not in auto_sync._WATERMARK_KINDS)
    ck("quick kind is not a full-history kind", "org_quick" not in auto_sync._FULL_KINDS)

    # Control: the same run under the scheduled kind DOES move it, so the check
    # above is one that could have failed.
    await add_run("org_recent", 0)
    after_recent = await plan()
    ck("control: an org_recent run at the same moment does move the watermark",
       after_recent["since"] > before["since"], f"{before['since']} -> {after_recent['since']}")

    async with maker() as s:
        await s.execute(text("DELETE FROM organisations WHERE id = :i"), {"i": org_id})
        await s.commit()
    await engine.dispose()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


asyncio.run(main())
