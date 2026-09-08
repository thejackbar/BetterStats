"""Twenty is gone; the engagement score, the CRM and Sales Management are not.

Asked for directly: *"the calculation and continual re-calculation of engagement
score and updating of CRM, and Sales Management functions is essential and both
manual export and background updating functions for CRM, Sales Management and
Club Directory must be preserved whilst retiring Twenty and its points of
integration."*

So this suite is in two halves, and the second is the point of it:

  1. NOTHING REACHES THE RETIRED CRM any more — no module, no setting, no route,
     no scheduled job, and nothing that would raise the first time a club paid
     for something.
  2. EVERY PRESERVED PATH ACTUALLY RUNS, against a real Postgres, through the
     SHIPPED functions: the nightly rescore, the Club Directory's own Refresh,
     the operator script's sweep, and the per-club rescore a send / a
     subscription change / an open fires.

The half that cannot be proved by reading the code is (2). The sweep used to be
gated on the external CRM and returned immediately when it was unconfigured —
which is exactly the state the platform is in now — so "it still runs" is a
claim that has to be executed, not asserted.

    python -m verification.verify_twenty_retirement
"""

from __future__ import annotations

import asyncio
import datetime as dt
import importlib.util
import os
import sys
import uuid

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))          # backend/, for `import app.*`
ROOT = os.path.dirname(os.path.dirname(_HERE))      # the repo root, for src()

DB_URL = os.environ.get(
    "VERIFY_DATABASE_URL",
    "postgresql+asyncpg://postgres@127.0.0.1:55432/verify_retire",
)
# MUST be set before app.models.db is imported — async_session_maker is built at
# import time from settings, and the sweep opens its own session through it.
os.environ["DATABASE_URL"] = DB_URL
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import func, select, text  # noqa: E402
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine  # noqa: E402

PASS: list[str] = []
FAIL: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(name if ok else f"{name} — {detail}")
    print(f"  {'PASS' if ok else 'FAIL'}  {name}{'' if ok else f'  ({detail})'}")


def head(t: str) -> None:
    print(f"\n── {t} " + "─" * max(0, 58 - len(t)))


def src(rel: str) -> str:
    """A shipped file's text, or '' when it is gone — so a control run REPORTS
    rather than dying on the first missing file."""
    try:
        return open(os.path.join(ROOT, rel)).read()
    except OSError:
        return ""


def module_gone(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is None
    except (ImportError, ModuleNotFoundError, ValueError):
        return True


# ── The lifespan's own raw-SQL tables ────────────────────────────────────────
# ``usage_events`` and ``platform_settings`` are created by main.py's lifespan,
# not by the ORM, so they are invisible to ``Base.metadata.create_all`` and the
# harness has to build them. Every column added to one since it was written
# lives in its OWN later ALTER, so taking the CREATE alone leaves a table that
# merely LOOKS right — both are pulled out of the shipped ``main.py`` rather
# than retyped, so they cannot go stale.

LIFESPAN_TABLES = ("usage_events", "platform_settings",
                   "marketing_utm_aliases")


def lifespan_ddl(table: str) -> list:
    import re
    main = src("backend/app/main.py")
    out: list = []
    m = re.search(rf"(CREATE TABLE IF NOT EXISTS {table} \(.*?\n\s*\))", main, re.S)
    if m:
        out.append(m.group(1))
    out += re.findall(rf"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS \w+ [A-Z ]+", main)
    # The loop-driven ALTERs, whose (column, type) pairs sit in a tuple an
    # f-string reads. Missing these is how a table's later columns go absent.
    loop = re.search(rf"for _col, _type in \((.*?)\n\s*\):\n\s*await conn\.execute\("
                     rf"text\(\n\s*f\"ALTER TABLE {table}", main, re.S)
    if loop:
        for col, typ in re.findall(r'\("(\w+)",\s*"([A-Z ]+)"\)', loop.group(1)):
            out.append(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {typ}")
    return out


# ══ 1. Nothing reaches the retired CRM ════════════════════════════════════════

RETIRED_MODULES = [
    "app.services.twenty_sync",
    "app.services.twenty_client",
    "app.services.twenty_leads_tasks",
    "app.services.twenty_inbound",
    "app.services.twenty_opportunity",
    "app.routers.pipeline_gauge",
    "app.scripts.bootstrap_twenty",
    "app.scripts.import_twenty_pipeline",
    "app.scripts.reconcile_twenty",
    "app.scripts.diagnose_club_lead",
    "app.scripts.engagement_lead_breakdown",
]

RETIRED_SETTINGS = [
    "twenty_api_url", "twenty_api_key", "twenty_webhook_secret",
    "twenty_rate_per_min", "twenty_task_assignee_id", "twenty_configured",
    "twenty_webhook_configured", "gauge_username", "gauge_password",
]


def structural_checks() -> None:
    head("Nothing reaches the retired CRM")

    for mod in RETIRED_MODULES:
        check(f"{mod.rsplit('.', 1)[-1]} is gone", module_gone(mod))

    from app.config.settings import settings
    leftover = [k for k in RETIRED_SETTINGS if hasattr(settings, k)]
    check("no external-CRM credential is a setting any more", not leftover,
          f"still present: {leftover}")

    main = src("backend/app/main.py")
    check("the gauge router is not mounted", bool(main) and "pipeline_gauge" not in main)
    check("a fresh database is not given the id-mapping ledger",
          bool(main) and "CREATE TABLE IF NOT EXISTS twenty_links" not in main)
    # The ledger is history: kept where it already exists, never dropped.
    check("...and nothing drops that ledger either",
          bool(main) and "DROP TABLE IF EXISTS twenty_links" not in main)

    sched = src("backend/app/jobs/scheduler.py")
    check("no lead/task scan is scheduled",
          bool(sched) and "refresh_twenty_leads_tasks" not in sched)
    check("the nightly rescore IS scheduled",
          "daily_engagement_rescore" in sched)
    check("...and it calls the one local sweep", "recalc_all_engagement" in sched)
    check("...not gated on an external CRM being configured",
          bool(sched) and "twenty_configured" not in sched)

    mkt = src("backend/app/routers/marketing.py")
    check("the export-to-external-CRM route is gone",
          bool(mkt) and "/export-twenty" not in mkt)
    check("the lead/task refresh route is gone",
          bool(mkt) and "refresh-twenty-leads-tasks" not in mkt)
    check("the Club Directory keeps its own rescore route",
          '"/refresh-engagement"' in mkt)
    check("...running the SAME sweep as the nightly job",
          "recalc_all_engagement" in mkt)
    check("the Club Directory keeps its push-to-CRM export",
          "/push-to-crm" in mkt)
    check("...and its export to BetterComms", "/export-comms" in mkt)

    api = src("frontend/src/lib/api.js")
    check("the browser can no longer call a retired route",
          bool(api) and "export-twenty" not in api and "refresh-twenty" not in api)
    check("...and can call the rescore", "refresh-engagement" in api)

    ui = src("frontend/src/pages/admin/SuperMarketing.jsx")
    check("the Club Directory offers a rescore button",
          "Refresh engagement scores" in ui and "mktRefreshEngagement" in ui)
    check("...and its push-to-CRM button is untouched", "mktPushToCrm" in ui)
    check("...and nothing on screen still names the retired CRM",
          bool(ui) and "Twenty" not in ui)


def call_site_checks() -> None:
    """Every subscription/onboarding hook must call something that EXISTS.

    This is the class of break neither a build nor an import smoke test catches:
    ``from x import y`` inside a function body compiles and imports fine, and
    only raises the first time a club actually pays for something."""
    head("Every hook calls something that exists")

    from app.routers import club_admin
    check("club_admin exposes the CRM sync helper",
          callable(getattr(club_admin, "_sync_club_to_crm", None)))
    check("...and no longer exposes the retired push",
          not hasattr(club_admin, "_push_club_to_twenty"))

    for rel, why in [
        ("backend/app/routers/billing.py", "a club adds modules to a live subscription"),
        ("backend/app/services/stripe_billing.py", "a Stripe payment lands"),
        ("backend/app/routers/organisations.py", "a club's first sync completes"),
    ]:
        s = src(rel)
        name = rel.rsplit("/", 1)[-1]
        check(f"{name} — {why} — syncs the CRM", "_sync_club_to_crm" in s)
        check(f"...and never calls the retired push ({name})",
              bool(s) and "_push_club_to_twenty" not in s)


# ══ 2. The preserved paths actually run ═══════════════════════════════════════

async def behavioural_checks() -> None:
    # A CONTROL RUN THAT CRASHES IS NOT A CONTROL RUN. Against a build where the
    # engagement engine still lives under its old name, or the shared sweep does
    # not exist yet, this half must REPORT that rather than dying on the first
    # import and saying nothing about the twenty-odd checks below it.
    import importlib
    missing = []
    try:
        engagement = importlib.import_module("app.services.engagement")
    except ImportError:
        engagement = None
        missing.append("services/engagement.py")
    from app.models.db import Base, MarketingClub
    from app.services import crm as crm_service
    if not callable(getattr(crm_service, "recalc_all_engagement", None)):
        missing.append("crm.recalc_all_engagement")
    if missing:
        check("the engagement engine and the shared sweep are both present",
              False, "missing: " + ", ".join(missing))
        print("  (skipping the behavioural half — nothing to run it against)")
        return

    engine = create_async_engine(DB_URL)
    Session = async_sessionmaker(engine, expire_on_commit=False)
    ddl = [stmt for t in LIFESPAN_TABLES for stmt in lifespan_ddl(t)]
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        for stmt in ddl:
            await conn.execute(text(stmt))

    now = dt.datetime.now(dt.timezone.utc)

    async with Session() as db:
        # Two directory-only prospects — no Organisation row, which is the
        # ordinary shape for a club nobody has onboarded: one with real recent
        # web activity, one nobody has ever visited.
        busy = MarketingClub(id=uuid.uuid4(), name="Busy CC",
                             grassroots_guid=f"g-{uuid.uuid4()}", utm_code="busycc")
        quiet = MarketingClub(id=uuid.uuid4(), name="Quiet CC",
                              grassroots_guid=f"g-{uuid.uuid4()}", utm_code="quietcc")
        db.add_all([busy, quiet])
        await db.flush()

        visitors = [uuid.uuid4() for _ in range(5)]
        for i in range(12):
            await db.execute(text(
                "INSERT INTO usage_events (created_at, event_type, method, path, "
                "status, visitor_id, utm_id) VALUES (:ts, 'page_view', 'GET', "
                "'/features', 200, CAST(:vid AS uuid), 'busycc')"),
                {"ts": now - dt.timedelta(days=(i % 4)), "vid": str(visitors[i % 5])})
        await db.commit()

        check("the harness built the lifespan's own tables from the shipped DDL",
              len(ddl) > 5 and all(any(t in d for d in ddl) for t in LIFESPAN_TABLES),
              f"only {len(ddl)} statement(s) extracted")

        head("The score is computed and cached, with no external CRM anywhere")
        before = busy.engagement_score
        payload = await engagement._engagement(db, busy)
        await db.commit()
        await db.refresh(busy)
        check("a club with real activity scores above zero",
              (busy.engagement_score or 0) > 0, f"score={busy.engagement_score}")
        check("...and the score is CACHED onto the club row, not just returned",
              busy.engagement_score == payload.get("engagementScore"),
              f"row={busy.engagement_score} payload={payload.get('engagementScore')}")
        check("...with the scored-at stamp the screens read",
              busy.engagement_scored_at is not None)
        check("...and it moved off whatever it was before",
              before != busy.engagement_score)
        check("a club with no activity at all still scores rather than erroring",
              (await engagement._engagement(db, quiet)).get("engagementScore") is not None)
        await db.commit()

        head("The nightly job and the Refresh button: one sweep, and it runs")
        await db.execute(text("UPDATE marketing_clubs SET engagement_score = NULL, "
                              "engagement_tier = NULL, engagement_scored_at = NULL"))
        await db.commit()
        # A raw UPDATE leaves the ORM's in-memory copy stale, so the sweep would
        # load a club that still LOOKS scored and write nothing — the harness
        # measuring itself rather than the code.
        db.expire_all()
        progress: dict = {}
        out = await crm_service.recalc_all_engagement(db, progress=progress)
        check("the sweep reaches every club in the directory",
              out["total"] == 2 and out["processed"] == 2, str(out))
        check("...with no club erroring", out["errors"] == 0, str(out))
        await db.refresh(busy)
        await db.refresh(quiet)
        check("...and every club's score is cached afterwards",
              busy.engagement_score is not None and quiet.engagement_score is not None)
        check("...the busy club scoring above the club nobody has visited",
              (busy.engagement_score or 0) > (quiet.engagement_score or 0),
              f"busy={busy.engagement_score} quiet={quiet.engagement_score}")
        check("the sweep reports progress a polling screen can render",
              progress.get("total") == 2 and "processed" in progress, str(progress))

        head("A dry run computes and persists nothing")
        await db.execute(text("UPDATE marketing_clubs SET engagement_score = NULL"))
        await db.commit()
        db.expire_all()
        dry = await crm_service.recalc_all_engagement(db, dry_run=True)
        check("a dry run still walks every club", dry["processed"] == 2, str(dry))
        async with Session() as fresh:
            still_null = (await fresh.execute(
                select(func.count()).select_from(MarketingClub)
                .where(MarketingClub.engagement_score.is_(None)))).scalar_one()
        check("...and writes nothing", still_null == 2,
              f"{still_null} of 2 still unscored")

        head("A single club rescores on its own signal")
        # The shape a BetterComms send, a subscription change and an open/click
        # all use: one club, no sweep.
        await db.execute(text("UPDATE marketing_clubs SET engagement_score = NULL"))
        await db.commit()
        # Refresh rather than expire: an expired instance handed to a service
        # lazy-loads on its first attribute read, which in an async request is
        # the MissingGreenlet trap this codebase documents.
        await db.refresh(busy)
        await db.refresh(quiet)
        await crm_service.sync_engagement_promotion(db, busy, None)
        await db.commit()
        await db.refresh(busy)
        check("the per-club rescore caches a score", busy.engagement_score is not None)
        await db.refresh(quiet)
        check("...and touches only that club", quiet.engagement_score is None)

        head("The operator script runs the SAME sweep, not a second one")
        from app.scripts import recalc_engagement as script
        # Read recalc()'s OWN body, not the whole file — the --verify /
        # --verify-fast equivalence checkers below it legitimately keep a loop
        # of their own, and a whole-file match would report them as the sweep.
        import inspect
        recalc_body = inspect.getsource(script.recalc)
        check("the script delegates to the shared sweep",
              "recalc_all_engagement" in recalc_body)
        check("...rather than keeping a second copy of the sweep loop",
              "for cid, cname in rows" not in recalc_body)
        res = await script.recalc(dry_run=True)
        check("the script's dry run walks every club", res["processed"] == 2, str(res))
        check("...and reports the distribution an operator reads",
              "scores" in res and "tiers" in res and "on_board" in res)

    await engine.dispose()


async def main() -> None:
    print("=" * 62)
    print("  Twenty retired; engagement, CRM and Sales Management preserved")
    print("=" * 62)
    structural_checks()
    call_site_checks()
    await behavioural_checks()
    print("\n" + "=" * 62)
    print(f"  {len(PASS)} passed, {len(FAIL)} failed")
    print("=" * 62)
    if FAIL:
        for f in FAIL:
            print("  FAILED:", f)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
