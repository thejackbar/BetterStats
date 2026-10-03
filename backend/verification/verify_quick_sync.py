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
  · the route asks for FRESH data (match lists and scorecards straight from
    Cricket Australia); Sync Now does not
  · an incremental run does not fetch a scorecard for a fixture that has not
    been played yet (the real game pass, real Postgres, stubbed CA responses).
    Control: the whole-history run over the same fixtures DOES fetch them
  · fresh=True reaches both the match-list and the scorecard reads; fresh=False
    leaves them on the cache
  · the grade match-list cache expires. Control: with the expiry removed, a
    list fetched earlier is still served long after (the old behaviour)

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
           len(a) >= 2 and a[-2] == today - timedelta(days=7), str(a))
        ck("task asks for fresh data", bool(a) and a[-1] is True, str(a))
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

    async def fake_sync_organisation(oid, run_id=None, kind="org_full", since=None, fresh=False):
        seen.append({"kind": kind, "since": since, "fresh": fresh})
        return {"games_new": 0}

    async def fake_finish(run_id, stats, error=None):
        return None

    real_sync, real_finish = orgs.sync_organisation, sync_mod.finish_sync_run
    orgs.sync_organisation = fake_sync_organisation
    sync_mod.finish_sync_run = fake_finish
    try:
        want = date(2026, 9, 26)
        await orgs._sync_safe(str(org_id), uuid.uuid4(), "org_quick", False, want, True)
        ck("_sync_safe forwards since and fresh to sync_organisation",
           seen and seen[-1] == {"kind": "org_quick", "since": want, "fresh": True}, str(seen))
        await orgs._sync_safe(str(org_id), uuid.uuid4(), "org_full")
        ck("Sync Now still passes no since (whole history) and no fresh",
           seen[-1] == {"kind": "org_full", "since": None, "fresh": False}, str(seen[-1]))
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


    # ---- the real game pass: fixtures not yet played, and fresh reads ---------
    await _game_pass_checks(maker, engine)

    # ---- the grade match-list cache expires ------------------------------------
    await _cache_ttl_checks()

    async with maker() as s:
        await s.execute(text("DELETE FROM organisations WHERE id = :i"), {"i": org_id})
        await s.commit()
    await engine.dispose()

    print(f"\n{PASS} passed, {FAIL} failed")
    sys.exit(1 if FAIL else 0)


async def apply_lifespan_ddl(engine):
    """Run the DDL strings out of main.py's lifespan, so the harness has the
    raw-SQL columns the game pass reads (a harness table that merely looks
    right is worse than none). Each statement is idempotent by construction."""
    import re
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "app", "main.py")).read()
    stmts = []
    for m in re.finditer(r'(?:"""|")\s*((?:ALTER TABLE|CREATE TABLE IF NOT EXISTS|CREATE UNIQUE INDEX IF NOT EXISTS|CREATE INDEX IF NOT EXISTS)[\s\S]*?)(?:"""|")\s*[,)\n]', src):
        st = m.group(1).strip()
        if "{" not in st and "%s" not in st:
            stmts.append(st)
    for _ in range(3):
        for st in stmts:
            try:
                async with engine.begin() as c:
                    await c.execute(text(st))
            except Exception:
                pass


async def _game_pass_checks(maker, engine):
    from app.services import grassroots_scores_client as gr
    from app.services import sync as sync_mod
    from app.models.db import Season, Grade, Organisation

    await apply_lifespan_ddl(engine)
    org = uuid.uuid4()
    season_id, grade_id = uuid.uuid4(), uuid.uuid4()
    grade_guid = str(uuid.uuid4())
    today = datetime.now(timezone.utc).date()

    def day(n):
        return (today + timedelta(days=n)).isoformat()

    fixtures = {  # name -> (match id, date offset)
        "older than the window": (str(uuid.uuid4()), -20),
        "yesterday": (str(uuid.uuid4()), -1),
        "today": (str(uuid.uuid4()), 0),
        "tomorrow (timezone slack)": (str(uuid.uuid4()), 1),
        "in three days": (str(uuid.uuid4()), 3),
        "in thirty days": (str(uuid.uuid4()), 30),
    }

    def match_list():
        return [{
            "id": mid, "status": "COMPLETED" if off <= 0 else "UPCOMING", "matchType": "T20",
            "round": {"name": "Round 1"},
            "matchSchedule": [{"startDateTime": f"{day(off)}T14:00:00.0000000+08:00"}],
            "teams": [{"owningOrganisation": {"id": str(org)}, "displayName": "Us"},
                      {"owningOrganisation": {"id": str(uuid.uuid4())}, "displayName": "Them"}],
        } for mid, off in fixtures.values()]

    async with maker() as s:
        await s.execute(text("INSERT INTO organisations (id, name, is_active) VALUES (:i, 'Game Pass CC', true)"), {"i": org})
        await s.commit()
        s.add(Season(id=season_id, organisation_id=org, grassroots_id=str(uuid.uuid4()), name="Summer", year=today.year))
        await s.commit()
        s.add(Grade(id=grade_id, season_id=season_id, name="Colts T20", grassroots_id=grade_guid))
        await s.commit()

    list_calls, card_calls = [], []

    async def fake_list(gid, *, force=False):
        list_calls.append(force)
        return match_list()

    async def fake_card(mid, *, force=False):
        card_calls.append((mid, force))
        return None   # nothing to ingest; only WHICH matches get asked about matters here

    real_list, real_card = gr.get_grade_matches, gr.get_match_scorecard
    gr.get_grade_matches, gr.get_match_scorecard = fake_list, fake_card
    try:
        async def run(since, fresh):
            list_calls.clear(); card_calls.clear()
            await sync_mod.sync_grassroots_game_level_data(
                str(org), since=since, season_ids=[season_id] if since else None, fresh=fresh)
            return {m for m, _ in card_calls}

        ids = {name: mid for name, (mid, _) in fixtures.items()}
        asked = await run(today - timedelta(days=7), True)
        names = lambda got: sorted(n for n, m in ids.items() if m in got)
        ck("incremental asks about yesterday, today and tomorrow",
           {ids["yesterday"], ids["today"], ids["tomorrow (timezone slack)"]} <= asked, names(asked))
        ck("incremental does NOT ask about fixtures 3 or 30 days away",
           ids["in three days"] not in asked and ids["in thirty days"] not in asked, names(asked))
        ck("incremental does NOT ask about a fixture older than the window",
           ids["older than the window"] not in asked, names(asked))
        ck("fresh=True reaches the match-list read", list_calls == [True], str(list_calls))
        ck("fresh=True reaches every scorecard read", card_calls and all(f for _, f in card_calls), str(card_calls))

        full = await run(None, False)
        ck("control: the whole-history run DOES ask about the future fixtures",
           ids["in thirty days"] in full and ids["in three days"] in full, names(full))
        ck("fresh=False leaves both reads on the cache",
           list_calls == [False] and all(not f for _, f in card_calls), f"{list_calls} {card_calls}")
    finally:
        gr.get_grade_matches, gr.get_match_scorecard = real_list, real_card
        async with maker() as s:
            await s.execute(text("DELETE FROM organisations WHERE id = :i"), {"i": org})
            await s.commit()


async def _cache_ttl_checks():
    from app.services import grassroots_scores_client as gr

    class _R:
        status_code = 200
        def __init__(self, n): self.n = n
        def json(self): return {"matches": [{"id": f"call-{self.n}"}]}

    calls = []

    async def fake_get(url, params=None):
        calls.append(url)
        return _R(len(calls))

    real_get, real_time, real_ttl = gr._get, gr.time.time, gr._GRADE_MATCHES_TTL
    clock = [1_000_000.0]
    gr._get = fake_get
    gr.time.time = lambda: clock[0]
    try:
        gr._grade_matches_cache.clear()
        a = await gr.get_grade_matches("g-ttl")
        b = await gr.get_grade_matches("g-ttl")
        ck("two reads inside the TTL make one request", len(calls) == 1 and a == b, str(calls))
        clock[0] += gr._GRADE_MATCHES_TTL + 1
        c = await gr.get_grade_matches("g-ttl")
        ck("a read after the TTL asks Cricket Australia again", len(calls) == 2 and c != a, f"{len(calls)} {c}")
        d = await gr.get_grade_matches("g-ttl", force=True)
        ck("force=True always re-reads", len(calls) == 3 and d != c, str(len(calls)))

        # Control: remove the expiry and the stale list comes straight back.
        gr._GRADE_MATCHES_TTL = 10 ** 12
        clock[0] += 5 * 3600
        e = await gr.get_grade_matches("g-ttl")
        ck("control: with no expiry, a list five hours old is still served (the old behaviour)",
           len(calls) == 3 and e == d, f"{len(calls)}")
    finally:
        gr._get, gr.time.time, gr._GRADE_MATCHES_TTL = real_get, real_time, real_ttl
        gr._grade_matches_cache.clear()


asyncio.run(main())
