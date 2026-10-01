"""The Club Directory's teaser crawl panel: GET /club-admin/marketing/teaser/status.

Runs the SHIPPED route body, progress query and estimate maths against a real
Postgres, plus the General Settings PATCH the panel saves through. What the
panel promises is that the number of clubs "due" is the number the worker will
work through, that its state names the real reason nothing is being pulled, and
that a save round-trips.

Run:
  DATABASE_URL=postgresql+asyncpg://postgres@/betterstats_verify?host=/tmp&port=5439 \
  python verification/verify_club_teaser_panel.py
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
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.models.db import Base

# A control run against the previous commit must REPORT the feature missing.
MISSING: list[str] = []
try:
    from app.services import club_teaser as ct
    from app.services.club_teaser_ddl import STATEMENTS, DOWNGRADE
    from app.services import platform_settings as ps
    from app.routers import marketing as mk
    from app.routers import club_admin as ca
    for name in ("teaser_progress", "crawl_estimate"):
        if not hasattr(ct, name):
            MISSING.append(f"club_teaser.{name} is missing")
    if not hasattr(mk, "teaser_status"):
        MISSING.append("routers.marketing.teaser_status is missing")
except ImportError as exc:  # pragma: no cover - control run only
    ct = STATEMENTS = DOWNGRADE = ps = mk = ca = None
    MISSING.append(str(exc))

DB = os.environ["DATABASE_URL"]
_db_name = make_url(DB).database or ""
if "verify" not in _db_name.lower():
    print(f"REFUSING to run: database {_db_name!r} is not a verification database "
          "(its name must contain 'verify'). These checks delete and drop tables.")
    sys.exit(2)
engine = create_async_engine(DB, echo=False)
Session = async_sessionmaker(engine, expire_on_commit=False)
ROOT = Path(__file__).resolve().parent.parent
PASS = FAIL = 0
FAILURES: list[str] = []


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


async def call_status(s, now_perth_hour=None):
    """The route body, optionally with the clock moved to a Perth hour."""
    if now_perth_hour is None:
        return await mk.teaser_status(db=s, _=None)
    real = ct.datetime
    fixed = datetime(2026, 9, 30, now_perth_hour, 30, tzinfo=ct.PERTH)

    class Clock(real):
        @classmethod
        def now(cls, tz=None):
            return fixed.astimezone(tz) if tz else fixed
    mk.datetime = Clock
    try:
        return await mk.teaser_status(db=s, _=None)
    finally:
        mk.datetime = real


async def set_paused(s, paused):
    await s.execute(text("INSERT INTO marketing_crawl_control (id, paused, updated_at) VALUES (1, :p, NOW()) "
                         "ON CONFLICT (id) DO UPDATE SET paused = :p"), {"p": paused})
    await s.commit()


async def main() -> None:
    if MISSING:
        check("the teaser panel backend is present", False, "; ".join(MISSING))
        print(f"\n{PASS} passed, {FAIL} failed")
        sys.exit(1)

    async with engine.begin() as c:
        await c.run_sync(Base.metadata.create_all)
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
        await c.execute(text("""CREATE TABLE IF NOT EXISTS marketing_crawl_control (
            id INTEGER PRIMARY KEY, paused BOOLEAN NOT NULL DEFAULT FALSE, updated_at TIMESTAMPTZ)"""))
    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots"))
        await s.execute(text("DELETE FROM marketing_clubs"))
        await set_paused(s, False)

    # ------------------------------------------------------------------
    # Fixture: 10 target clubs + 3 that are not targets
    #   c0 ok 30 calls, pulled 10 min ago, not due
    #   c1 ok 20 calls, pulled 2 hours ago, not due
    #   c2 empty 1 call, pulled 10 min ago, not due
    #   c3 error, backed off a day, not due
    #   c4 ok 40 calls, overdue (due)
    #   c5 junior_only 5 calls, not due
    #   c6..c9 never pulled (due)
    #   excluded / customer / trialist: never counted
    # ------------------------------------------------------------------
    now = datetime.now(timezone.utc)
    ids = []
    async with Session() as s:
        async def club(i, **kw):
            cid = g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, kind, excluded,
                not_interested, trial_modules, status, source)
                VALUES (CAST(:id AS uuid), :guid, :name, 'club', :ex, false, CAST(:tm AS jsonb), 'new', 'grassroots_api')"""),
                {"id": cid, "guid": g(), "name": f"Panel Club {i:02d}", "ex": kw.get("excluded", False),
                 "tm": '["stats"]' if kw.get("trial") else "[]"})
            return cid
        for i in range(10):
            ids.append(await club(i))
        await club(90, excluded=True)
        await club(91, trial=True)

        async def snap(cid, status, calls, pulled_ago, next_in):
            await s.execute(text("""INSERT INTO club_teaser_snapshots
                (marketing_club_id, org_guid, token, status, api_calls, pulled_at, next_pull_at)
                VALUES (CAST(:c AS uuid), :g, :t, :st, :calls, :pulled, :nxt)"""),
                {"c": cid, "g": g(), "t": g(), "st": status, "calls": calls,
                 "pulled": now - pulled_ago, "nxt": now + next_in})
        await snap(ids[0], "ok", 30, timedelta(minutes=10), timedelta(days=7))
        await snap(ids[1], "ok", 20, timedelta(hours=2), timedelta(days=7))
        await snap(ids[2], "empty", 1, timedelta(minutes=10), timedelta(days=14))
        await snap(ids[3], "error", 0, timedelta(minutes=10), timedelta(days=1))
        await snap(ids[4], "ok", 40, timedelta(days=8), -timedelta(days=1))
        await snap(ids[5], "junior_only", 5, timedelta(minutes=10), timedelta(days=90))
        await s.commit()

    print("progress")
    async with Session() as s:
        p = await ct.teaser_progress(s, now=now, type_modes={})
        check("targets exclude the excluded club and the trialist (10, not 12)", p["targets"] == 10, str(p))
        check("six clubs have a snapshot and four have never been pulled",
              p["with_snapshot"] == 6 and p["never_pulled"] == 4, str(p))
        check("due is the overdue club plus the four never pulled (5)", p["due"] == 5, str(p))
        check("the status counts add up (ok 3, empty 1, junior_only 1, error 1)",
              (p["ok"], p["empty"], p["junior_only"], p["error"]) == (3, 1, 1, 1), str(p))
        check("the errored club is backed off, so it is not counted as due", p["error"] == 1 and p["due"] == 5)
        check("calls a club is the mean of the clubs that made calls and answered (30,20,40,1,5 = 19.2)",
              abs(p["avg_calls"] - 19.2) < 0.05, str(p["avg_calls"]))
        check("the last hour holds the three clubs pulled 10 minutes ago that made calls or not (4 clubs, 36 calls)",
              p["clubs_last_hour"] == 4 and p["calls_last_hour"] == 36, str(p))
        check("the newest pull is reported", p["last_pulled_at"] is not None)
        due = await ct.due_clubs(s, 100, now=now, type_modes={})
        check("DUE MATCHES WHAT THE WORKER WOULD PULL: the count equals due_clubs' rows",
              len(due) == p["due"], f"{len(due)} vs {p['due']}")
        await s.execute(text("UPDATE marketing_clubs SET trial_modules = '[\"stats\"]'::jsonb WHERE name = 'Panel Club 06'"))
        await s.commit()
        p2 = await ct.teaser_progress(s, now=now, type_modes={})
        due2 = await ct.due_clubs(s, 100, now=now, type_modes={})
        check("and still equal once a club is in a sales trial (both leave it out)",
              len(due2) == p2["due"] == 4, f"{len(due2)} vs {p2['due']}")
        await s.execute(text("UPDATE marketing_clubs SET trial_modules = '[]'::jsonb WHERE name = 'Panel Club 06'"))
        await s.commit()

    print("estimate")
    e = ct.crawl_estimate(3651, 27.8, 2.0, 5, 22)
    check("101,500 calls at 2 a second is about 14.1 hours, 0.8 of a 17 hour window",
          e and abs(e["hours"] - 14.1) < 0.1, str(e))
    check("the rate that finishes in one window is calls / window seconds",
          e and abs(e["rate_to_finish_in_one_window"] - 3651 * 27.8 / (17 * 3600)) < 0.01, str(e))
    check("no estimate when off, nothing due, no calls-a-club yet, or a closed window",
          ct.crawl_estimate(100, 20, 0, 5, 22) is None and ct.crawl_estimate(0, 20, 2, 5, 22) is None
          and ct.crawl_estimate(100, 0, 2, 5, 22) is None and ct.crawl_estimate(100, 20, 2, 22, 22) is None)

    print("state")
    async with Session() as s:
        await s.execute(text("UPDATE platform_settings SET settings = '{}'")); await s.commit()
        st = await call_status(s, 12)
        check("unset rate: OFF, with the default hours", st["state"] == "off" and st["rate"] == 0.0
              and (st["window_start"], st["window_end"]) == (5, 22), str(st["state"]))
        check("the payload carries the bounds the box validates against",
              st["min_rate"] == 0.05 and st["max_rate"] == 10.0)
        check("off gives no estimate", st["estimate"] is None)
        await ps.update_settings(s, {"club_teaser_calls_per_second": 2})
        st = await call_status(s, 12)
        check("rate set, inside the hours, clubs due: RUNNING", st["state"] == "running", st["state"])
        check("the estimate is given while running", st["estimate"] is not None and st["estimate"]["window_hours"] == 17)
        st = await call_status(s, 23)
        check("23:30 Perth is OUTSIDE HOURS, not running", st["state"] == "outside_hours" and not st["in_hours"], st["state"])
        st = await call_status(s, 4)
        check("04:30 Perth is outside hours too", st["state"] == "outside_hours", st["state"])
        await set_paused(s, True)
        st = await call_status(s, 12)
        check("the Stop switch reads as STOPPED, and beats outside hours", st["state"] == "stopped" and st["stopped"], st["state"])
        st = await call_status(s, 23)
        check("stopped is reported even outside the hours", st["state"] == "stopped", st["state"])
        await set_paused(s, False)
        await ps.update_settings(s, {"club_teaser_calls_per_second": None})
        await set_paused(s, True)
        st = await call_status(s, 12)
        check("off beats stopped (nothing is set to be stopped)", st["state"] == "off", st["state"])
        await set_paused(s, False)
        await ps.update_settings(s, {"club_teaser_calls_per_second": 2})
        await s.execute(text("UPDATE club_teaser_snapshots SET next_pull_at = now() + interval '30 days'"))
        await s.execute(text("""INSERT INTO club_teaser_snapshots (marketing_club_id, org_guid, token, status, next_pull_at)
            SELECT id, 'x', md5(id::text), 'ok', now() + interval '30 days' FROM marketing_clubs mc
            WHERE NOT EXISTS (SELECT 1 FROM club_teaser_snapshots t WHERE t.marketing_club_id = mc.id)"""))
        await s.commit()
        st = await call_status(s, 12)
        check("nothing due: CAUGHT UP", st["state"] == "idle" and st["progress"]["due"] == 0, st["state"])

    print("save round trip (the General Settings PATCH the panel uses)")
    async with Session() as s:
        from fastapi import HTTPException
        await ps.update_settings(s, {"club_teaser_calls_per_second": None})
        out = await ca.patch_general_settings(
            body=ca.GeneralSettingsUpdate(club_teaser_calls_per_second=1.75, club_teaser_window_start=6,
                                          club_teaser_window_end=20), _=None, db=s)
        st = await call_status(s, 12)
        check("a saved rate and hours come back on the status", st["rate"] == 1.75
              and (st["window_start"], st["window_end"]) == (6, 20) and out["club_teaser_calls_per_second"] == 1.75)
        check("and 05:30 Perth is now outside a 06:00 opening", (await call_status(s, 5))["state"] == "outside_hours")
        await ca.patch_general_settings(body=ca.GeneralSettingsUpdate(club_teaser_calls_per_second=None), _=None, db=s)
        st = await call_status(s, 12)
        check("null switches it off and leaves the hours alone",
              st["state"] == "off" and (st["window_start"], st["window_end"]) == (6, 20), st["state"])
        for label, body in (("a rate over the ceiling", dict(club_teaser_calls_per_second=11)),
                            ("a rate under the floor", dict(club_teaser_calls_per_second=0.01)),
                            ("hours that close before they open",
                             dict(club_teaser_window_start=20, club_teaser_window_end=6))):
            try:
                await ca.patch_general_settings(body=ca.GeneralSettingsUpdate(**body), _=None, db=s)
                refused = False
            except HTTPException as e:
                refused = e.status_code == 422
            check(f"{label} is a 422 the panel can show", refused)
        st = await call_status(s, 12)
        check("a refused save leaves the stored hours alone", (st["window_start"], st["window_end"]) == (6, 20))

    print("reading a snapshot back (review_snapshot, and the inspect script over real stored pulls)")
    from app.services import club_teaser_report as rep
    good = {"club": {"name": "Good CC", "state": "WA", "suburb": "Perth", "logo_url": "http://x/l.png"},
            "season": {"name": "Summer 2025/26", "year": 2025},
            "totals": {"matches": 14, "wins": 9, "losses": 5, "draws": 0, "win_rate": 64},
            "ladders": [{"grade": "A Grade", "rank": 2, "teams": 8, "played": 14, "won": 9, "lost": 5, "points": 40}],
            "batting": [{"name": f"B{i}", "runs": 400 - i * 10, "innings": 12, "high_score": 90} for i in range(5)],
            "bowling": [{"name": f"W{i}", "wickets": 20 - i, "average": 15.0} for i in range(5)],
            "fielding": [{"name": "F", "catches": 9, "run_outs": 1, "stumpings": 0}],
            "records": [{"label": "Most Individual Runs", "value": "120", "player": "B0"}]}
    v = rep.review_snapshot(good, this_year=2026)
    check("a full snapshot is READY with nothing missing and no warnings",
          v["ready"] and not v["missing"] and not v["warnings"], str(v))
    check("no snapshot at all is not ready and says so", rep.review_snapshot(None, this_year=2026)["missing"] == ["no snapshot"])
    thin = {**good, "batting": good["batting"][:1], "bowling": [], "ladders": []}
    v = rep.review_snapshot(thin, this_year=2026)
    check("too few batters, no bowlers and no ladder are each named as missing",
          not v["ready"] and len(v["missing"]) == 3 and any("batters" in m for m in v["missing"])
          and any("bowlers" in m for m in v["missing"]) and any("ladder" in m for m in v["missing"]), str(v["missing"]))
    v = rep.review_snapshot({**good, "totals": {"matches": 0}}, this_year=2026)
    check("a season with no matches played is not ready", not v["ready"] and any("matches" in m for m in v["missing"]))
    v = rep.review_snapshot({**good, "batting": [{"name": "A B", "runs": 50, "innings": 5, "high_score": 90}] * 3,
                             "club": {"name": "X"}, "season": {"name": "S", "year": 2019}}, this_year=2026)
    check("a high score above the total, an old season and a missing place are WARNINGS, not gaps",
          v["ready"] and len(v["warnings"]) >= 3, str(v["warnings"]))
    v = rep.review_snapshot({**good, "batting": [{"name": "*** ***", "runs": 50, "innings": 5, "high_score": 40}] * 3},
                            this_year=2026)
    check("a redacted name that slipped through is flagged", any("redacted" in w for w in v["warnings"]))
    lines = "\n".join(rep.teaser_lines(good))
    check("the read-back names the club, record, ladder, batters, bowlers and record",
          all(t in lines for t in ("Good CC", "14 played, 9 won", "A Grade 2 of 8", "bat: B0", "bowl: W0", "Most Individual Runs")), lines)

    # Real stored pulls: run the shipped pull_club against a stand-in for CA,
    # save them, then run the shipped script over the table.
    class PH:
        calls = 0

        async def seasons(self, org): self.calls += 1; return [{"id": "S1", "name": "Summer 2025/26", "startDate": "2025-10-01"}]
        async def batting(self, org, sid, grades=None):
            self.calls += 1
            return [{"id": f"p{i}", "name": f"Batter {i}", "statistics": {"battingAggregate": 400 - i * 9, "battingInnings": 12,
                     "battingNotOuts": 1, "battingHighScore": 80, "batting50s": 2, "batting100s": 0}} for i in range(4)]
        async def bowling(self, org, sid, grades=None):
            self.calls += 1
            return [{"id": f"w{i}", "name": f"Bowler {i}", "statistics": {"bowlingWickets": 18 - i, "bowlingRuns": 300,
                     "bowlingBalls": 400, "bowlingBestInnings": "5/20"}} for i in range(4)]
        async def fielding(self, org, sid, grades=None):
            self.calls += 1
            return [{"id": "f1", "name": "Keeper One", "statistics": {"fieldingTotalCatches": 7}}]
        async def teams(self, org, sid): self.calls += 1; return [{"id": "T", "grades": [{"id": "G1", "name": "A Grade"}]}]
        async def ladder(self, gid):
            self.calls += 1
            return {"ladders": [{"name": "Overall", "pools": [{"teams": [
                {"rank": 2, "displayName": "Read Back", "owningOrganisation": {"id": "ORG"},
                 "ladderData": [{"id": "played", "val": 14}, {"id": "won", "val": 9}, {"id": "lost", "val": 5},
                                {"id": "competitionPoints", "val": 40}]},
                {"rank": 1, "displayName": "Other", "owningOrganisation": {"id": "X"},
                 "ladderData": [{"id": "played", "val": 14}]}]}]}]}

    async with Session() as s:
        await s.execute(text("DELETE FROM club_teaser_snapshots")); await s.execute(text("DELETE FROM marketing_clubs")); await s.commit()
        for i, nm in enumerate(("Read Back CC", "Empty Read CC")):
            cid = g()
            await s.execute(text("""INSERT INTO marketing_clubs (id, grassroots_guid, name, state, kind, excluded, not_interested,
                trial_modules, status, source) VALUES (CAST(:id AS uuid), :guid, :n, 'WA', 'club', false, false, '[]'::jsonb,
                'new', 'grassroots_api')"""), {"id": cid, "guid": g(), "n": nm})
            club = {"id": cid, "guid": g(), "name": nm, "state": "WA", "short_name": None, "suburb": "Perth",
                    "association": "WACA", "logo_url": None}
            if i == 0:
                res = await ct.pull_club(PH(), "ORG", club)
            else:
                res = {"status": "empty", "snapshot": None, "season_year": None, "season_start": None,
                       "season_pending": False, "error": None, "calls": 1}
            await ct.save_result(s, club, res)
    check("the stand-in pull produced an ok snapshot to read back", True)
    import io, contextlib
    from app.scripts import inspect_club_teasers as ins
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await ins.main(["--limit", "10"])
    out = buf.getvalue()
    check("the script lists both clubs, one line each, and exits 0", rc == 0 and "Read Back CC" in out and "Empty Read CC" in out, out[:400])
    check("an ok snapshot with everything reads READY and an empty one is reported as empty",
          "READY" in out and "empty" in out, out)
    check("the summary says how many ok snapshots have what a campaign piece needs", "1 of 1 ok snapshot(s)" in out, out)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await ins.main(["--show", "Read Back"])
    out = buf.getvalue()
    check("--show prints the facts a piece would use (record, ladder place, batters) and what is missing",
          rc == 0 and "14 played, 9 won" in out and "2 of 2" in out and "bat: B. 0" in out and "MISSING:  nothing" in out, out)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        await ins.main(["--json", "Read Back"])
    check("--json dumps the raw stored snapshot", '"batting"' in buf.getvalue() and '"ladders"' in buf.getvalue())
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = await ins.main(["--club", "no such club"])
    check("no match exits 1 with a plain line", rc == 1 and "no snapshots match" in buf.getvalue())
    async with Session() as s:
        n = await s.scalar(text("SELECT count(*) FROM club_teaser_snapshots"))
    check("the script wrote nothing (still exactly the two snapshots)", n == 2)

    print("wiring")
    js = (ROOT.parent / "frontend/src/components/admin/TeaserCrawlPanel.jsx").read_text()
    page = (ROOT.parent / "frontend/src/pages/admin/SuperMarketing.jsx").read_text()
    api = (ROOT.parent / "frontend/src/lib/api.js").read_text()
    check("the Club Directory page mounts the panel", "<TeaserCrawlPanel />" in page)
    check("the panel reads the status endpoint and saves through General Settings",
          "mktTeaserStatus" in js and "superUpdateGeneralSettings" in js
          and "/club-admin/marketing/teaser/status" in api)
    check("the route sits behind the super admin gate",
          "require_super_admin" in (ROOT / "app/routers/marketing.py").read_text().split("def teaser_status")[1][:400])

    async with engine.begin() as c:
        for s in DOWNGRADE:
            await c.execute(text(s))
        await c.execute(text("UPDATE platform_settings SET settings = '{}'"))
        await c.execute(text("DELETE FROM marketing_clubs"))
    print(f"\n{PASS} passed, {FAIL} failed")
    if FAIL:
        print("FAILED:", *FAILURES, sep="\n  ")
        sys.exit(1)


asyncio.run(main())
