"""Verification for the Sales Performance all-time contact columns, against a
real Postgres.

Exercises the SHIPPED service functions and route bodies — never a
re-implementation of their logic — the way the rest of this repo's
verification suites do.

The reported case is the first thing it replays: nothing logged today or this
week, real work behind them, and a Contact activity table that said nothing at
all.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/bstest?host=/var/tmp&port=5433 \
      .venv/bin/python verify_sales_activity_all_time.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import (
    Base, CrmActivity, CrmDeal, CrmPipeline, CrmStage, MarketingClub, User,
)
from app.routers import sales_workspace as router
from app.routers.auth import SalesActor
from app.services import sales_workspace as sw

DB = os.environ["DATABASE_URL"]
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)

PASS = FAIL = 0
FAILURES: list[str] = []


def check(label, got, want=True):
    global PASS, FAIL
    if got == want:
        PASS += 1
        print(f"  ok   {label}")
    else:
        FAIL += 1
        FAILURES.append(f"{label}: got {got!r}, want {want!r}")
        print(f"  FAIL {label}: got {got!r}, want {want!r}")


async def build_schema():
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)


# ─── Fixture ─────────────────────────────────────────────────────────────────
# Perth days, because that is what report_windows resolves against — a UTC
# "yesterday" can still be today in Perth and would make these assertions
# quietly time-of-day dependent.
NOW = datetime.now(timezone.utc)
WINDOWS = sw.report_windows()
TODAY_START = WINDOWS["today"]
WEEK_START = WINDOWS["week"]

IDS: dict = {}


async def seed(session):
    pipeline = CrmPipeline(id=uuid.uuid4(), name="Platform", scope="platform")
    session.add(pipeline)
    stage = CrmStage(id=uuid.uuid4(), pipeline_id=pipeline.id, key="target",
                     name="Target", position=1)
    session.add(stage)

    reps = {}
    for key, name in (("sam", "Sam Barendse"), ("kate", "Kate Leary"), ("old", "Retired Rep")):
        u = User(id=uuid.uuid4(), username=key, email=f"{key}@example.com",
                 password_hash="x", display_name=name)
        session.add(u)
        reps[key] = u
    IDS["reps"] = reps

    deals = {}
    for key, club_name in (("a", "Alpha CC"), ("b", "Beta CC"), ("c", "Gamma CC")):
        club = MarketingClub(id=uuid.uuid4(), name=club_name, state="WA",
                             grassroots_guid=f"verify:{club_name}")
        session.add(club)
        deal = CrmDeal(id=uuid.uuid4(), scope="platform", pipeline_id=pipeline.id,
                       stage_id=stage.id, title=club_name, marketing_club_id=club.id,
                       owner_user_id=reps["sam"].id)
        session.add(deal)
        deals[key] = deal
    IDS["deals"] = deals
    await session.flush()

    def act(rep, deal, when, **kw):
        session.add(CrmActivity(id=uuid.uuid4(), deal_id=deals[deal].id,
                                created_by_user_id=reps[rep].id, occurred_at=when, **kw))

    long_ago = WEEK_START - timedelta(days=400)
    last_month = WEEK_START - timedelta(days=30)
    last_week = WEEK_START - timedelta(days=3)

    # ── Sam: real work, ALL of it behind this week's boundary ──
    act("sam", "a", long_ago, type="call", outcome="interested", body="1")
    act("sam", "a", last_month, type="call", outcome="interested", body="2")
    act("sam", "b", last_month, type="email", body="3")
    act("sam", "c", last_week, type="call", outcome="not_interested", body="4")
    # A follow-up booked off a note — contact, but neither a call nor an email.
    act("sam", "b", last_week, type="note", body="5",
        next_follow_up_at=NOW + timedelta(days=2))
    # Never counts: a general-outcome call is filed as a note, not contact.
    act("sam", "a", last_month, type="call", outcome="general_note", body="6")
    # Never counts: the Twenty cutover backfill is somebody else's pipeline.
    act("sam", "a", last_month, type="call", outcome="interested", body="7",
        meta={"twenty_kind": "opportunity"})
    # Never counts: an ordinary note with no follow-up.
    act("sam", "a", last_month, type="note", body="8")

    # ── Kate: one call, also historic, on a club Sam also rang ──
    act("kate", "a", last_month, type="call", outcome="interested", body="9")

    # ── Retired Rep: only a Twenty-imported row, so never appears at all ──
    act("old", "c", long_ago, type="email", body="10", meta={"twenty_note_id": "n1"})

    # ── Trials started (system rows, matched on the body prefix) ──
    session.add(CrmActivity(id=uuid.uuid4(), deal_id=deals["a"].id,
                            created_by_user_id=reps["sam"].id, occurred_at=last_month,
                            type="system", body=f"{sw.TRIAL_STARTED_ACTIVITY_PREFIX} Alpha CC"))
    await session.commit()


def row_for(report, name):
    return next((r for r in report["rows"] if r["name"] == name), None)


async def main():
    await build_schema()
    async with Session() as session:
        await seed(session)

        reps, deals = IDS["reps"], IDS["deals"]

        print("\n── report_windows ──")
        w = sw.report_windows()
        check("all-time window is present", sw.ALL_TIME_WINDOW in w)
        check("all-time has NO lower bound (None, never an epoch)", w[sw.ALL_TIME_WINDOW], None)
        check("the three windows, in screen order", sw.REPORT_WINDOWS,
              ("today", "week", "all"))
        check("today/week still resolve to instants",
              all(isinstance(w[k], datetime) for k in ("today", "week")))

        print("\n── the reported case: a quiet week, real history ──")
        report = await sw.activity_report(session)
        totals = report["totals"]
        check("nothing logged today", totals["today"]["contacts"], 0)
        check("nothing logged this week", totals["week"]["contacts"], 0)
        check("the table is NOT empty", len(report["rows"]) > 0)
        check("all-time contacts counted", totals["all"]["contacts"], 6)
        sam = row_for(report, "Sam Barendse")
        check("Sam is listed", sam is not None)
        check("Sam's all-time contacts", sam["all"]["contacts"], 5)
        check("Sam's today is zero", sam["today"]["contacts"], 0)
        check("Sam's week is zero", sam["week"]["contacts"], 0)

        print("\n── what counts as a contact, all time ──")
        check("calls (general-outcome and Twenty rows excluded)", sam["all"]["calls"], 3)
        check("emails", sam["all"]["emails"], 1)
        check("a follow-up on a note is contact, not a call or an email",
              sam["all"]["contacts"] - sam["all"]["calls"] - sam["all"]["emails"], 1)
        check("callbacks created", sam["all"]["callbacks_created"], 1)
        check("positive conversations", sam["all"]["positive_conversations"], 2)
        check("trials started", sam["all"]["trials_started"], 1)
        check("a rep with only Twenty-imported rows is never listed",
              row_for(report, "Retired Rep"), None)

        print("\n── clubs contacted is distinct, never a sum of per-rep counts ──")
        kate = row_for(report, "Kate Leary")
        check("Sam reached 3 clubs", sam["all"]["clubs_contacted"], 3)
        check("Kate reached 1 club", kate["all"]["clubs_contacted"], 1)
        check("the team reached 3 distinct clubs, not 4",
              totals["all"]["clubs_contacted"], 3)
        check("contacts DO sum across reps",
              sam["all"]["contacts"] + kate["all"]["contacts"], totals["all"]["contacts"])

        print("\n── the row order still leads on live work ──")
        check("all time only breaks a tie: Sam (5) above Kate (1)",
              [r["name"] for r in report["rows"]], ["Sam Barendse", "Kate Leary"])

        print("\n── one rep's own numbers ──")
        mine = await sw.activity_report(session, owner_user_id=reps["kate"].id)
        check("pinned to Kate, one row", [r["name"] for r in mine["rows"]], ["Kate Leary"])
        check("pinned all-time total is hers alone", mine["totals"]["all"]["contacts"], 1)
        check("performance_summary carries every window",
              sorted((await sw.performance_summary(session)).keys()), ["all", "today", "week"])

        print("\n── the drill-down behind an all-time figure ──")
        for metric, want in (("contacts", 6), ("calls", 4), ("emails", 1), ("clubs_contacted", 3)):
            res = await sw.activity_cell_clubs(
                session, user_id=sw.EVERYONE_KEY, window="all", metric=metric)
            check(f"'{metric}' total equals the figure clicked", res["total"], want)
            check(f"'{metric}' rows add up to it", sum(r["count"] for r in res["clubs"]), want)
        res = await sw.activity_cell_clubs(
            session, user_id=sw.EVERYONE_KEY, window="all", metric="clubs_contacted")
        check("clubs_contacted is one row per club", len(res["clubs"]), res["total"])
        check("every row names its club",
              sorted(r["club_name"] for r in res["clubs"]), ["Alpha CC", "Beta CC", "Gamma CC"])
        check("a row carries the deep link the Workspace takes",
              all(uuid.UUID(r["deal_id"]) for r in res["clubs"]))

        res = await sw.activity_cell_clubs(
            session, user_id=str(reps["sam"].id), window="all", metric="contacts")
        check("one rep's all-time drill-down matches their own cell",
              res["total"], sam["all"]["contacts"])
        res = await sw.activity_cell_clubs(
            session, user_id=sw.EVERYONE_KEY, window="today", metric="contacts")
        check("today's drill-down is still empty", res["total"], 0)

        print("\n── the windows a drill-down will answer ──")
        for window in sw.REPORT_WINDOWS:
            try:
                await sw.activity_cell_clubs(
                    session, user_id=sw.EVERYONE_KEY, window=window, metric="contacts")
                ok = True
            except ValueError:
                ok = False
            check(f"'{window}' accepted", ok)
        try:
            await sw.activity_cell_clubs(
                session, user_id=sw.EVERYONE_KEY, window="forever", metric="contacts")
            refused = False
        except ValueError:
            refused = True
        check("an unknown window is refused", refused)

        print("\n── the route bodies ──")
        super_actor = SalesActor(user=reps["sam"], role="super_admin")
        payload = await router.performance(actor=super_actor, db=session)
        check("summary carries all three windows",
              sorted(payload["summary"].keys()), ["all", "today", "week"])
        check("the KPI strip IS the table's totals row",
              payload["summary"]["all"], report["totals"]["all"])
        check("the activity rows are on the wire", len(payload["activity"]), 2)

        drill = await router.performance_drilldown(
            panel="activity", window="all", metric="contacts",
            user_id=sw.EVERYONE_KEY, actor=super_actor, db=session)
        check("the route's all-time drill-down agrees with the cell",
              drill["total"], payload["summary"]["all"]["contacts"])

        sales_actor = SalesActor(user=reps["kate"], role="sales")
        pinned = await router.performance(actor=sales_actor, db=session)
        check("a 'sales' caller sees only their own all-time work",
              pinned["summary"]["all"]["contacts"], 1)
        pinned_drill = await router.performance_drilldown(
            panel="activity", window="all", metric="contacts",
            user_id=str(reps["sam"].id), actor=sales_actor, db=session)
        check("…and cannot ask for another rep's, even naming them",
              pinned_drill["total"], 1)

        print("\n── the dated windows still separate, and all time contains them ──")
        # Perth midweek, so 'today' and 'week' genuinely differ — on the
        # Monday this was reported they are the same instant, which would
        # leave the split untested.
        midweek = sw.report_windows(datetime(2026, 8, 26, 4, 0, tzinfo=timezone.utc))
        check("midweek, today is after the week start",
              midweek["today"] > midweek["week"])
        check("and all time is still unbounded", midweek[sw.ALL_TIME_WINDOW], None)

        session.add(CrmActivity(id=uuid.uuid4(), deal_id=deals["a"].id,
                                created_by_user_id=reps["sam"].id,
                                occurred_at=TODAY_START + timedelta(minutes=30),
                                type="call", outcome="interested", body="today"))
        await session.commit()
        after = await sw.activity_report(session)
        check("a call logged today shows up today", after["totals"]["today"]["contacts"], 1)
        check("…and this week", after["totals"]["week"]["contacts"], 1)
        check("…and all time counts it too, on top of the history",
              after["totals"]["all"]["contacts"], 7)
        check("today's drill-down now finds it",
              (await sw.activity_cell_clubs(session, user_id=sw.EVERYONE_KEY,
                                            window="today", metric="calls"))["total"], 1)
        check("all-time calls include it",
              (await sw.activity_cell_clubs(session, user_id=sw.EVERYONE_KEY,
                                            window="all", metric="calls"))["total"], 5)

        print("\n── the lean row: an all-time pull must not drag email bodies ──")
        rows = await sw._contact_rows(session)
        keys = set(rows[0]._mapping.keys())
        check("no `meta` selected", "meta" not in keys)
        check("no `body` selected", "body" not in keys)
        check("the Twenty flag rides along instead", "twenty_imported" in keys)

        print("\n── the SQL Twenty test agrees with the Python one ──")
        by_body = {r.body: r for r in (await session.execute(
            text("SELECT body, meta FROM crm_activities"))).all()}
        flags = {r.body: r.twenty_imported for r in (await session.execute(
            text("SELECT body, (meta ? 'twenty_kind' OR meta ? 'twenty_note_id') "
                 "AS twenty_imported FROM crm_activities"))).all()}
        for body, row in by_body.items():
            class _A:
                meta = row.meta
            check(f"row {body!r} classified the same both ways",
                  bool(flags[body]), sw._is_twenty_imported(_A()))

        print("\n── contacted_deal_ids still agrees after the lean refactor ──")
        contacted = await sw.contacted_deal_ids(session, [d.id for d in deals.values()])
        check("all three clubs have been contacted", len(contacted), 3)
        check("Gamma is in it (a not_interested call is still contact)",
              deals["c"].id in contacted)

        # A club nobody has rung: contact must not be claimed for it.
        club = MarketingClub(id=uuid.uuid4(), name="Delta CC", state="WA",
                             grassroots_guid="verify:Delta CC")
        session.add(club)
        await session.flush()
        quiet = CrmDeal(id=uuid.uuid4(), scope="platform",
                        pipeline_id=deals["a"].pipeline_id, stage_id=deals["a"].stage_id,
                        title="Delta CC", marketing_club_id=club.id)
        session.add(quiet)
        await session.commit()
        contacted = await sw.contacted_deal_ids(session, [quiet.id])
        check("an unrung club is not contacted", contacted, set())

    print(f"\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    await engine.dispose()
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
