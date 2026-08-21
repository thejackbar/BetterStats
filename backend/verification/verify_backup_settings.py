"""Verification for the Backup settings page, against a real Postgres.

Exercises the SHIPPED route bodies (routers/backup_admin.py), the shipped
settings getters/setters (services/platform_settings.py), the shipped due
maths (services/backup_schedule.py) and the shipped host-script CLI
(app/scripts/backup_task.py) — never a re-implementation of any of them.

The backup-agent is the REAL one too (ops/backup/agent/app.py), mounted over
an in-process ASGI transport against a real temporary BACKUP_ROOT on disk, so
"delete these bundles" is verified end to end: the backend route, the agent
route, the files actually leaving the disk, and the task rows being stamped.

Run:  DATABASE_URL=postgresql+asyncpg://postgres@/backup_verify?host=/tmp/pgsock&port=5544 \
      python verification/verify_backup_settings.py
"""
from __future__ import annotations

import asyncio
import os
import re
import shutil
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SECRET_KEY", "verify-secret-key-for-tests-only")

BUNDLE_ROOT = tempfile.mkdtemp(prefix="backup-verify-root-")
os.environ["BACKUP_ROOT"] = BUNDLE_ROOT
os.environ["BACKUP_AGENT_SECRET"] = "verify-agent-secret"
os.environ["AGE_RECIPIENT"] = "age1verifyrecipient"

import httpx  # noqa: E402
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import text  # noqa: E402

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


async def status_of(coro):
    try:
        await coro
        return None
    except HTTPException as e:
        return e.status_code


class FakeUser:
    def __init__(self, uid):
        self.id = uid


# ── the real agent, reachable over an in-process ASGI transport ─────────────
# Loaded by path under its own name: the agent's file is itself called app.py,
# and putting its directory on sys.path would shadow this backend's `app`
# package.
import importlib.util  # noqa: E402

_agent_path = Path(__file__).resolve().parent.parent.parent / "ops/backup/agent/app.py"
_spec = importlib.util.spec_from_file_location("backup_agent_app", _agent_path)
agent_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(agent_module)


_REAL_ASYNC_CLIENT = httpx.AsyncClient  # captured before the module is patched


def _agent_client_factory(*args, **kwargs):
    """Stands in for httpx.AsyncClient inside backup_admin so its real
    requests reach the real agent app in-process, over ASGI."""
    kwargs.pop("timeout", None)
    return _REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=agent_module.app),
                              base_url="http://agent", **kwargs)


def write_bundle(name: str, *, db_bytes=1000, uploads_bytes=500, complete=True):
    d = Path(BUNDLE_ROOT) / name
    d.mkdir(parents=True, exist_ok=True)
    if complete:
        (d / "db.dump.age").write_bytes(b"x" * db_bytes)
    (d / "uploads.tar.zst.age").write_bytes(b"y" * uploads_bytes)
    (d / "manifest.json").write_text("{}")
    return d


async def main():
    from app.models.db import Base, async_session_maker, engine, Organisation, User
    import app.routers.backup_admin as ba
    from app.services import backup_schedule as bs, platform_settings as ps
    from app.config.settings import settings as app_settings

    app_settings.backup_agent_url = "http://agent"
    app_settings.backup_agent_secret = "verify-agent-secret"
    ba.httpx.AsyncClient = _agent_client_factory  # type: ignore[assignment]

    # ── schema: ORM tables + the raw-SQL ones the lifespan owns ─────────────
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS platform_settings (
                id INTEGER PRIMARY KEY DEFAULT 1 CHECK (id = 1),
                settings JSONB NOT NULL DEFAULT '{}',
                updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))
        await conn.execute(text(
            "INSERT INTO platform_settings (id, settings) VALUES (1, '{}') ON CONFLICT DO NOTHING"))
        # backup_tasks in its PRE-275 shape, so migration 275 has something to do.
        await conn.execute(text("""
            CREATE TABLE IF NOT EXISTS backup_tasks (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                task_type TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'requested',
                scope_org_id UUID REFERENCES organisations(id) ON DELETE SET NULL,
                triggered_by TEXT NOT NULL DEFAULT 'scheduled',
                triggered_by_user_id UUID REFERENCES users(id) ON DELETE SET NULL,
                bundle_path TEXT,
                bundle_timestamp TIMESTAMPTZ,
                started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                completed_at TIMESTAMPTZ,
                db_size_bytes BIGINT,
                uploads_size_bytes BIGINT,
                total_row_count BIGINT,
                club_stats JSONB,
                error_message TEXT,
                progress JSONB,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """))

    Session = async_session_maker

    print("\n── Migration 275, applied three times to a populated table ──")
    async with Session() as db:
        club = Organisation(id=uuid.uuid4(), name="Applecross Cricket Club", slug="applecross")
        user = User(id=uuid.uuid4(), username="super", email="s@b.com", password_hash="x")
        db.add_all([club, user])
        await db.flush()
        await db.execute(text(
            "INSERT INTO backup_tasks (task_type, status, bundle_path, triggered_by) "
            "VALUES ('backup', 'completed', '/mnt/media/bettercricket/backup/2026-01-01T19-00-00Z', 'scheduled')"))
        await db.commit()
        user_id = user.id

    mig = Path(__file__).resolve().parent.parent / "alembic/versions/275_backup_bundle_deletion.py"
    stmts = re.findall(r'op\.execute\(\s*"((?:[^"\\]|\\.)*)"', mig.read_text())
    stmts = [s for s in stmts if "ADD COLUMN" in s]
    check("migration 275 has three ADD COLUMN statements", len(stmts), 3)
    for run in range(3):
        async with engine.begin() as conn:
            for stmt in stmts:
                await conn.execute(text(stmt))
    async with Session() as db:
        cols = {r[0]: r[1] for r in (await db.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'backup_tasks'"))).all()}
        check("bundle_deleted_at added", cols.get("bundle_deleted_at"), "timestamp with time zone")
        check("bundle_deleted_by added", cols.get("bundle_deleted_by"), "uuid")
        check("bundle_deleted_reason added", cols.get("bundle_deleted_reason"), "text")
        rows = (await db.execute(text("SELECT COUNT(*) FROM backup_tasks"))).scalar()
        check("the existing row survived three applications", rows, 1)
        deleted = (await db.execute(text(
            "SELECT bundle_deleted_at FROM backup_tasks LIMIT 1"))).scalar()
        check("an existing row reads as 'still on disk' (NULL)", deleted, None)

    print("\n── The lifespan mirror lands on the same columns ──")
    main_src = (Path(__file__).resolve().parent.parent / "app/main.py").read_text()
    mirror = re.findall(r'"(ALTER TABLE backup_tasks ADD COLUMN IF NOT EXISTS bundle_deleted[^"]*)"\s*\n?\s*("[^"]*")?',
                        main_src)
    mirrored = []
    for whole, cont in mirror:
        mirrored.append(whole + (cont.strip('"') if cont else ""))
    check("the lifespan mirrors all three ALTERs", len(mirrored), 3)
    async with engine.begin() as conn:
        for stmt in mirrored:
            await conn.execute(text(stmt))  # idempotent — must not raise on an already-275 table

    print("\n── The schedule is Perth, and a legacy UTC row converts once ──")
    async with Session() as db:
        sched = await ps.get_backup_schedule(db)
        check("an unset schedule defaults to 03:00 Perth", (sched["hour"], sched["minute"]), (3, 0))
        check("...keeping 30 days", sched["retention_days"], 30)
        check("...and says which timezone that is", sched["timezone"], "Australia/Perth")

        # what a pre-Perth install has stored: the UTC hour, no tz marker
        await db.execute(text(
            "UPDATE platform_settings SET settings = "
            "'{\"backup_schedule\": {\"hour\": 19, \"minute\": 30, \"retention_days\": 30}}'::jsonb "
            "WHERE id = 1"))
        await db.commit()
        sched = await ps.get_backup_schedule(db)
        check("a legacy 19:00 UTC row reads as 03:00 Perth — the same real moment",
              (sched["hour"], sched["minute"]), (3, 30))

    print("\n── Saving from the screen: 7-day retention, a Perth time ──")
    async with Session() as db:
        payload = await ba.update_backup_settings(
            ba.BackupSettingsUpdate(retention_days=7), _=FakeUser(user_id), db=db)
        check("retention saved as 7", payload["schedule"]["retention_days"], 7)
        check("the legacy hour was not converted a second time on save",
              payload["schedule"]["hour"], 3)
        payload = await ba.update_backup_settings(
            ba.BackupSettingsUpdate(hour=21, minute=15), _=FakeUser(user_id), db=db)
        check("a Perth hour is stored verbatim", (payload["schedule"]["hour"], payload["schedule"]["minute"]),
              (21, 15))
        check("retention is untouched by an hour-only save", payload["schedule"]["retention_days"], 7)
        raw = (await db.execute(text(
            "SELECT settings -> 'backup_schedule' FROM platform_settings WHERE id = 1"))).scalar()
        check("the stored row is stamped Perth", raw.get("tz"), "Australia/Perth")
        check("the stored hour IS the Perth hour", raw.get("hour"), 21)
        again = await ps.get_backup_schedule(db)
        check("re-reading a saved row converts nothing", (again["hour"], again["minute"]), (21, 15))

    print("\n── What the settings screen refuses ──")
    async with Session() as db:
        check("hour 24 is refused",
              await status_of(ba.update_backup_settings(
                  ba.BackupSettingsUpdate(hour=24), _=FakeUser(user_id), db=db)), 400)
        check("minute 60 is refused",
              await status_of(ba.update_backup_settings(
                  ba.BackupSettingsUpdate(minute=60), _=FakeUser(user_id), db=db)), 400)
        check("0 days retention is refused",
              await status_of(ba.update_backup_settings(
                  ba.BackupSettingsUpdate(retention_days=0), _=FakeUser(user_id), db=db)), 400)
        check("a decade of retention is refused",
              await status_of(ba.update_backup_settings(
                  ba.BackupSettingsUpdate(retention_days=4000), _=FakeUser(user_id), db=db)), 400)
        after = await ps.get_backup_schedule(db)
        check("a refused save changed nothing", (after["hour"], after["minute"], after["retention_days"]),
              (21, 15, 7))
        # hour 0 and minute 0 are real values, not "unset"
        payload = await ba.update_backup_settings(
            ba.BackupSettingsUpdate(hour=0, minute=0), _=FakeUser(user_id), db=db)
        check("midnight Perth is settable", (payload["schedule"]["hour"], payload["schedule"]["minute"]), (0, 0))
        await ba.update_backup_settings(ba.BackupSettingsUpdate(hour=3, minute=0),
                                        _=FakeUser(user_id), db=db)

    print("\n── When the next run is due (Perth), and catching up a missed one ──")
    sched = {"hour": 3, "minute": 30}
    P = bs.PERTH
    before = datetime(2026, 8, 21, 2, 0, tzinfo=P)
    after = datetime(2026, 8, 21, 4, 0, tzinfo=P)
    check("not due before the configured time", bs.is_due(sched, None, before)[0], False)
    check("due once the time has passed", bs.is_due(sched, None, after)[0], True)
    late = datetime(2026, 8, 21, 23, 45, tzinfo=P)
    check("a missed slot is caught up later the same day, not skipped",
          bs.is_due(sched, None, late)[0], True)
    done_today = datetime(2026, 8, 21, 3, 31, tzinfo=P)
    check("not due again once today's backup has completed",
          bs.is_due(sched, done_today, late)[0], False)
    # A completion is a TIMESTAMPTZ, so it can arrive as UTC — 19:31Z on the
    # 20th IS 03:31 Perth on the 21st, and must count as today's.
    done_utc = datetime(2026, 8, 20, 19, 31, tzinfo=timezone.utc)
    check("a UTC-stored completion is judged on its PERTH day",
          bs.is_due(sched, done_utc, after)[0], False)
    check("next run is today's slot when it hasn't come round yet",
          bs.next_run_at(sched, before), datetime(2026, 8, 21, 3, 30, tzinfo=P))
    check("next run rolls to tomorrow once today's is done",
          bs.next_run_at(sched, after, done_today), datetime(2026, 8, 22, 3, 30, tzinfo=P))
    check("a schedule near midnight resolves on the right Perth day",
          bs.next_run_at({"hour": 23, "minute": 50}, datetime(2026, 8, 21, 23, 55, tzinfo=P), None),
          datetime(2026, 8, 21, 23, 50, tzinfo=P))

    print("\n── The settings payload the screen reads ──")
    async with Session() as db:
        await db.execute(text(
            "INSERT INTO backup_tasks (task_type, status, started_at, completed_at, bundle_path) "
            "VALUES ('backup', 'completed', NOW() - INTERVAL '2 hours', NOW() - INTERVAL '2 hours', "
            "'/mnt/media/bettercricket/backup/2026-02-02T19-00-00Z')"))
        await db.commit()
        payload = await ba.get_backup_settings(_=FakeUser(user_id), db=db)
        check("it reports when the backup last completed", payload["last_completed_at"] is not None, True)
        check("it reports a next run", payload["next_run_at"] is not None, True)
        check("the next run is in the future", payload["next_run_at"] > bs.perth_now(), True)
        check("it says the retention bounds the screen should offer",
              (payload["retention_min_days"], payload["retention_max_days"]), (1, 365))
        check("it says the agent is configured", payload["agent_configured"], True)

    print("\n── What's on disk: the file list ──")
    write_bundle("2026-08-21T19-00-00Z", db_bytes=2000, uploads_bytes=1000)
    write_bundle("2026-08-20T19-00-00Z", db_bytes=1500, uploads_bytes=800)
    write_bundle("2026-06-01T19-00-00Z", db_bytes=1200, uploads_bytes=700)
    write_bundle("2026-05-01T19-00-00Z", db_bytes=400, uploads_bytes=100, complete=False)
    (Path(BUNDLE_ROOT) / "not-a-bundle").mkdir(exist_ok=True)

    async with Session() as db:
        # one task row per bundle, except the June one (a run from before task
        # logging) and one row whose bundle is already gone
        for stamp in ("2026-08-21T19-00-00Z", "2026-08-20T19-00-00Z"):
            await db.execute(text(
                "INSERT INTO backup_tasks (task_type, status, bundle_path, triggered_by, total_row_count) "
                "VALUES ('backup', 'completed', :p, 'scheduled', 12345) ON CONFLICT DO NOTHING"),
                {"p": f"/mnt/media/bettercricket/backup/{stamp}"})
        await db.commit()
        files = await ba.list_backup_files(_=FakeUser(user_id), db=db)
        names = [b["bundle"] for b in files["bundles"]]
        check("every bundle on disk is listed, newest first", names,
              ["2026-08-21T19-00-00Z", "2026-08-20T19-00-00Z", "2026-06-01T19-00-00Z", "2026-05-01T19-00-00Z"])
        check("a directory that isn't a bundle is ignored", "not-a-bundle" in names, False)
        check("sizes are the real bytes on disk", files["bundles"][0]["size_bytes"], 2000 + 1000 + 2)
        check("the total is the sum of them", files["total_size_bytes"],
              sum(b["size_bytes"] for b in files["bundles"]))
        check("a bundle with no database dump is flagged incomplete",
              files["bundles"][3]["complete"], False)
        check("a bundle is matched to the task that wrote it",
              files["bundles"][0]["task_id"] is not None, True)
        check("a bundle with no task row is still listed",
              files["bundles"][2]["task_id"], None)
        check("...and says so rather than inventing a trigger",
              files["bundles"][2]["triggered_by"], None)
        missing = [b["bundle"] for b in files["missing"]]
        check("a task whose files have gone is reported as history, not as disk",
              "2026-08-20T19-00-00Z" in missing, False)
        check("...the older run with no directory left is",
              "2026-01-01T19-00-00Z" in missing, True)
        check("the backup root is named for the screen", files["backup_root"], BUNDLE_ROOT)

    print("\n── Deleting bundles ──")
    async with Session() as db:
        st = await status_of(ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=[]), user=FakeUser(user_id), db=db))
        check("deleting nothing is refused", st, 400)
        st = await status_of(ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=["../../etc"]), user=FakeUser(user_id), db=db))
        check("a path-traversal name is refused outright", st, 400)
        check("...and nothing left the disk", (Path(BUNDLE_ROOT) / "2026-06-01T19-00-00Z").is_dir(), True)

        st = await status_of(ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=["2026-08-21T19-00-00Z"]), user=FakeUser(user_id), db=db))
        check("deleting the most recent backup needs a second confirmation", st, 400)
        check("...and it is still there", (Path(BUNDLE_ROOT) / "2026-08-21T19-00-00Z").is_dir(), True)

        res = await ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=["2026-06-01T19-00-00Z", "2026-05-01T19-00-00Z"]),
            user=FakeUser(user_id), db=db)
        check("two older bundles delete in one go", res["deleted_count"], 2)
        check("nothing failed", res["failed_count"], 0)
        check("the freed bytes are real", res["freed_bytes"], 1200 + 700 + 2 + 100 + 2)
        check("the June bundle's files are gone",
              (Path(BUNDLE_ROOT) / "2026-06-01T19-00-00Z").exists(), False)
        check("the May bundle's files are gone",
              (Path(BUNDLE_ROOT) / "2026-05-01T19-00-00Z").exists(), False)
        check("the ones not selected are untouched",
              sorted(p.name for p in Path(BUNDLE_ROOT).iterdir() if p.name != "not-a-bundle"),
              ["2026-08-20T19-00-00Z", "2026-08-21T19-00-00Z"])

        # one real, one already gone — the good one must still be deleted
        res = await ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=["2026-08-20T19-00-00Z", "2026-07-04T19-00-00Z"]),
            user=FakeUser(user_id), db=db)
        check("a bundle that isn't there doesn't stop the rest", res["deleted_count"], 1)
        check("...and is reported by name", res["failed_count"], 1)
        check("...naming which one", [r["bundle"] for r in res["results"] if r["status"] == "failed"],
              ["2026-07-04T19-00-00Z"])

        row = (await db.execute(text(
            "SELECT bundle_deleted_at, bundle_deleted_by, bundle_deleted_reason FROM backup_tasks "
            "WHERE bundle_path LIKE '%2026-08-20T19-00-00Z'"))).first()
        check("the task row is stamped deleted", row[0] is not None, True)
        check("...by whom", row[1], user_id)
        check("...and that a person did it", row[2], "manual")
        kept = (await db.execute(text(
            "SELECT COUNT(*) FROM backup_tasks WHERE bundle_path LIKE '%2026-08-20T19-00-00Z'"))).scalar()
        check("the run's history row is kept, only its files went", kept, 1)

    print("\n── A deleted bundle can't be downloaded or restored ──")
    async with Session() as db:
        task_id = (await db.execute(text(
            "SELECT id FROM backup_tasks WHERE bundle_path LIKE '%2026-08-20T19-00-00Z'"))).scalar()
        check("resolving it for a download/restore is refused",
              await status_of(ba._resolve_bundle(db, str(task_id))), 410)
        live_id = (await db.execute(text(
            "SELECT id FROM backup_tasks WHERE bundle_path LIKE '%2026-08-21T19-00-00Z'"))).scalar()
        check("a bundle still on disk resolves normally",
              await ba._resolve_bundle(db, str(live_id)), "2026-08-21T19-00-00Z")
        tasks = await ba.list_backup_tasks(task_type="backup", status=None, limit=50, offset=0,
                                           _=FakeUser(user_id), db=db)
        deleted_row = next(t for t in tasks["tasks"] if str(task_id) == t["id"])
        check("the Backups page is told the files are gone",
              deleted_row["bundle_deleted_at"] is not None, True)
        live_row = next(t for t in tasks["tasks"] if str(live_id) == t["id"])
        check("...and that a live bundle's are not", live_row["bundle_deleted_at"], None)

    print("\n── Deleting the newest, deliberately ──")
    async with Session() as db:
        res = await ba.delete_backup_files(
            ba.DeleteBundlesRequest(bundles=["2026-08-21T19-00-00Z"], include_latest=True),
            user=FakeUser(user_id), db=db)
        check("with the extra confirmation, the newest deletes", res["deleted_count"], 1)
        check("the backup root is now empty of bundles",
              [p.name for p in Path(BUNDLE_ROOT).iterdir() if p.name != "not-a-bundle"], [])
        files = await ba.list_backup_files(_=FakeUser(user_id), db=db)
        check("the file list reports an empty disk", files["bundles"], [])
        check("...and every past run as history with no files", len(files["missing"]) >= 3, True)

    print("\n── The host script's own questions ──")
    from app.scripts import backup_task as bt
    async with Session() as db:
        await db.execute(text("UPDATE backup_tasks SET status = 'failed' WHERE status = 'completed'"))
        await db.commit()
    sched_now = None
    async with Session() as db:
        sched_now = await ps.get_backup_schedule(db)
    check("get-schedule hands the host script Perth values", (sched_now["hour"], sched_now["minute"]), (3, 0))
    async with Session() as db:
        last = await bt._last_completed_backup(db)
        check("with no completed backup, there is nothing to call today's", last, None)
        due, _reason = bs.is_due(sched_now, last, datetime.now(bs.PERTH).replace(hour=23, minute=0))
        check("so a tick late in the day says run", due, True)
        await db.execute(text(
            "INSERT INTO backup_tasks (task_type, status, started_at, completed_at, bundle_path) "
            "VALUES ('backup', 'completed', NOW(), NOW(), "
            "'/mnt/media/bettercricket/backup/2026-09-09T19-00-00Z')"))
        await db.commit()
        last = await bt._last_completed_backup(db)
        due, _reason = bs.is_due(sched_now, last, datetime.now(bs.PERTH).replace(hour=23, minute=0))
        check("once one has completed today, the next tick does nothing", due, False)

    print("\n── Retention pruning stamps what it removed ──")
    async with Session() as db:
        await db.execute(text(
            "INSERT INTO backup_tasks (task_type, status, bundle_path) VALUES "
            "('backup', 'completed', '/mnt/media/bettercricket/backup/2026-03-03T19-00-00Z')"))
        await db.commit()
    await bt._mark_bundle_deleted("2026-03-03T19-00-00Z", "retention")
    async with Session() as db:
        row = (await db.execute(text(
            "SELECT bundle_deleted_at, bundle_deleted_reason FROM backup_tasks "
            "WHERE bundle_path LIKE '%2026-03-03T19-00-00Z'"))).first()
        check("a pruned bundle's row is stamped", row[0] is not None, True)
        check("...and says it was retention, not a person", row[1], "retention")
        before = row[0]
    await bt._mark_bundle_deleted("2026-03-03T19-00-00Z", "retention")
    async with Session() as db:
        again = (await db.execute(text(
            "SELECT bundle_deleted_at FROM backup_tasks "
            "WHERE bundle_path LIKE '%2026-03-03T19-00-00Z'"))).scalar()
        check("re-running the prune doesn't move the deletion date", again, before)
        untouched = (await db.execute(text(
            "SELECT COUNT(*) FROM backup_tasks WHERE bundle_deleted_at IS NULL"))).scalar()
        check("a bundle name only stamps its own row", untouched >= 1, True)

    print("\n── The agent refuses what it should ──")
    async with _REAL_ASYNC_CLIENT(transport=httpx.ASGITransport(app=agent_module.app),
                                  base_url="http://agent") as c:
        r = await c.get("/bundles")
        check("no secret, no listing", r.status_code, 403)
        r = await c.post("/delete-bundle", json={"bundle": "2026-08-21T19-00-00Z"},
                         headers={"X-Agent-Secret": "wrong"})
        check("a wrong secret cannot delete", r.status_code, 403)
        r = await c.post("/delete-bundle", json={"bundle": "../../../etc"},
                         headers={"X-Agent-Secret": "verify-agent-secret"})
        check("a traversal name is refused by the agent too", r.status_code, 400)
        r = await c.post("/delete-bundle", json={"bundle": "2020-01-01T00-00-00Z"},
                         headers={"X-Agent-Secret": "verify-agent-secret"})
        check("deleting a bundle that isn't there is a plain 404", r.status_code, 404)

    print("\n── Control: what the old hour-only check did with the same schedule ──")
    # backup.sh used to compare the UTC hour ONLY, and skip the day outright
    # if the tick didn't land inside it — so the configured MINUTE never
    # decided anything, and a tick pattern that stepped past the hour cost a
    # whole day's backup. Replayed here (this is the OLD logic, not shipped
    # code) against the same schedule the new check is asked about above.
    def old_should_run(sched_hour, now_utc_hour):
        return now_utc_hour == sched_hour

    sched_utc_hour = (3 - 8) % 24  # 03:00 Perth as the old code stored it
    check("old: a tick inside the scheduled hour ran", old_should_run(sched_utc_hour, 19), True)
    check("old: a tick one hour later skipped the whole day",
          old_should_run(sched_utc_hour, 20), False)
    missed = datetime(2026, 8, 21, 4, 30, tzinfo=P)   # 20:30 UTC — past the hour
    check("new: the same missed slot is caught up instead",
          bs.is_due({"hour": 3, "minute": 0}, None, missed)[0], True)
    check("old: the configured minute could not affect the decision",
          old_should_run(sched_utc_hour, 19), old_should_run(sched_utc_hour, 19))
    check("new: it can — before the minute, not due",
          bs.is_due({"hour": 3, "minute": 45}, None, datetime(2026, 8, 21, 3, 30, tzinfo=P))[0], False)

    shutil.rmtree(BUNDLE_ROOT, ignore_errors=True)
    print(f"\n{'='*60}\n{PASS} passed, {FAIL} failed")
    for f in FAILURES:
        print(f"  - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
