"""CLI used by the host backup/restore scripts (ops/backup/backup.sh,
ops/backup/restore.sh) to read the configured schedule and to log each run
into ``backup_tasks``. Invoked via ``docker compose exec -T
betterstats-backend python -m app.scripts.backup_task ...`` — this is how a
host-level shell script (no app import, no DB driver of its own) gets at the
app's own Postgres session and the backup_stats snapshot logic.

Usage:
  # prints "HOUR MINUTE RETENTION_DAYS" (space-separated, easy for bash to
  # `read` into three variables). HOUR/MINUTE are PERTH local time — that is
  # what a super admin set on the Backup settings page, and what is stored.
  python -m app.scripts.backup_task get-schedule

  # prints "1 <reason>" when a scheduled backup is due right now, else
  # "0 <reason>" — the host timer ticks every 15 minutes and asks this before
  # doing any real work. All the Perth-time reasoning lives in
  # services/backup_schedule.py, never in the shell script.
  python -m app.scripts.backup_task should-run

  # creates a backup_tasks row, prints its id (only the id, to stdout)
  python -m app.scripts.backup_task start-task --type backup --triggered-by scheduled
  python -m app.scripts.backup_task start-task --type restore_full --triggered-by manual

  # marks a task completed, stamping the current DB/per-club stats plus
  # whatever the shell script measured on disk
  python -m app.scripts.backup_task finish-task <task_id> --status completed \\
      --bundle-path /mnt/media/bettercricket/backup/2026-07-21T03-00-00Z --uploads-size-bytes 12345

  # marks a task failed
  python -m app.scripts.backup_task finish-task <task_id> --status failed --error "pg_dump exited 1"

  # prints "1" (a backup completed today, PERTH day) or "0" — the
  # already-ran-today half of should-run, on its own for BACKUP_FORCE=1
  python -m app.scripts.backup_task has-run-today

  # stamps a task's bundle as no longer on disk, so the Backups page stops
  # offering a download/restore of files that have been pruned or deleted
  python -m app.scripts.backup_task mark-bundle-deleted 2026-08-21T19-00-00Z --reason retention

  # prints "table<TAB>approx_row_count" lines (from pg_stat_user_tables — an
  # ESTIMATE, cheap, not a full COUNT(*) scan) so the calling shell script can
  # build a progress reference before starting pg_dump/pg_restore
  python -m app.scripts.backup_task table-counts

  # live progress while a task is running — see app/services/backup_progress.py
  python -m app.scripts.backup_task update-progress <task_id> --stage players --current 3 --total 70
  python -m app.scripts.backup_task mark-stage-done <task_id> --stage players --count 876
"""
import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import backup_progress, backup_schedule, backup_stats, platform_settings as ps


async def _last_completed_backup(session):
    """When the most recent backup actually finished (TIMESTAMPTZ, so it
    carries its own zone) — the input to every "already done today" check."""
    row = (await session.execute(text(
        "SELECT COALESCE(completed_at, started_at) FROM backup_tasks "
        "WHERE task_type = 'backup' AND status = 'completed' "
        "ORDER BY COALESCE(completed_at, started_at) DESC LIMIT 1"
    ))).first()
    return row[0] if row else None


async def _get_schedule():
    async with async_session_maker() as session:
        sched = await ps.get_backup_schedule(session)
    print(f"{sched['hour']} {sched['minute']} {sched['retention_days']}")


async def _should_run():
    async with async_session_maker() as session:
        sched = await ps.get_backup_schedule(session)
        last = await _last_completed_backup(session)
    due, reason = backup_schedule.is_due(sched, last)
    print(f"{1 if due else 0} {reason}")


async def _start_task(task_type: str, triggered_by: str, scope_org_id: str | None,
                       triggered_by_user_id: str | None):
    async with async_session_maker() as session:
        row = (await session.execute(
            text(
                "INSERT INTO backup_tasks (task_type, status, scope_org_id, triggered_by, triggered_by_user_id) "
                "VALUES (:t, 'running', :org, :tb, :user) RETURNING id"
            ),
            {"t": task_type, "org": scope_org_id, "tb": triggered_by, "user": triggered_by_user_id},
        )).first()
        await session.commit()
        print(str(row[0]))


async def _finish_task(task_id: str, status: str, bundle_path: str | None,
                        uploads_size_bytes: int | None, error: str | None):
    async with async_session_maker() as session:
        stats = {}
        if status == "completed":
            try:
                stats = await backup_stats.compute_db_stats(session)
            except Exception as e:  # never let a stats hiccup turn a real success into "failed"
                stats = {}
                error = error or f"(stats snapshot failed: {e})"
        await session.execute(
            text(
                "UPDATE backup_tasks SET status = :status, completed_at = NOW(), "
                "bundle_path = COALESCE(:bundle_path, bundle_path), "
                "bundle_timestamp = CASE WHEN :bundle_path IS NOT NULL THEN NOW() ELSE bundle_timestamp END, "
                "db_size_bytes = :db_size, uploads_size_bytes = COALESCE(:uploads_size, uploads_size_bytes), "
                "total_row_count = :total_rows, club_stats = CAST(:club_stats AS jsonb), "
                "error_message = :error "
                "WHERE id = :id"
            ),
            {
                "status": status,
                "bundle_path": bundle_path,
                "db_size": stats.get("db_size_bytes"),
                "uploads_size": uploads_size_bytes,
                "total_rows": stats.get("total_row_count"),
                "club_stats": json.dumps(stats.get("club_stats")) if stats.get("club_stats") is not None else None,
                "error": error,
                "id": task_id,
            },
        )
        await session.commit()


async def _has_run_today():
    """PERTH day, not the server's — the schedule is Perth-local, so "today"
    has to be too or a backup scheduled near the UTC date boundary reads as
    yesterday's."""
    async with async_session_maker() as session:
        last = await _last_completed_backup(session)
    print("1" if backup_schedule.completed_on(backup_schedule.perth_now().date(), last) else "0")


async def _mark_bundle_deleted(bundle: str, reason: str):
    """Stamps every completed backup task whose bundle_path ends in this
    bundle name. Matches on the directory NAME rather than the full path so a
    BACKUP_ROOT that has since moved doesn't leave rows unstampable."""
    async with async_session_maker() as session:
        result = await session.execute(text(
            "UPDATE backup_tasks SET bundle_deleted_at = COALESCE(bundle_deleted_at, NOW()), "
            "bundle_deleted_reason = COALESCE(bundle_deleted_reason, :reason) "
            "WHERE task_type = 'backup' AND bundle_path IS NOT NULL "
            "AND regexp_replace(bundle_path, '/+$', '') LIKE :suffix"
        ), {"reason": reason, "suffix": f"%/{bundle}"})
        await session.commit()
        print(result.rowcount or 0)


async def _table_counts():
    async with async_session_maker() as session:
        rows = (await session.execute(text(
            "SELECT relname, n_live_tup FROM pg_stat_user_tables ORDER BY relname"
        ))).all()
        for name, count in rows:
            print(f"{name}\t{max(count or 0, 0)}")


async def _update_progress(task_id: str, stage: str, current: int, total: int, message: str | None):
    async with async_session_maker() as session:
        await backup_progress.set_progress(
            session, task_id, stage=stage, current=current, total=total, message=message
        )


async def _mark_stage_done(task_id: str, stage: str, count: int):
    async with async_session_maker() as session:
        await backup_progress.mark_stage_done(session, task_id, stage, count)


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("get-schedule")
    sub.add_parser("should-run")
    sub.add_parser("has-run-today")

    p_deleted = sub.add_parser("mark-bundle-deleted")
    p_deleted.add_argument("bundle")
    p_deleted.add_argument("--reason", default="retention",
                           choices=["retention", "manual"])
    sub.add_parser("table-counts")

    p_progress = sub.add_parser("update-progress")
    p_progress.add_argument("task_id")
    p_progress.add_argument("--stage", required=True)
    p_progress.add_argument("--current", type=int, required=True)
    p_progress.add_argument("--total", type=int, required=True)
    p_progress.add_argument("--message", default=None)

    p_stage_done = sub.add_parser("mark-stage-done")
    p_stage_done.add_argument("task_id")
    p_stage_done.add_argument("--stage", required=True)
    p_stage_done.add_argument("--count", type=int, required=True)

    p_start = sub.add_parser("start-task")
    p_start.add_argument("--type", required=True, choices=["backup", "restore_full", "restore_club"])
    p_start.add_argument("--triggered-by", default="scheduled", choices=["scheduled", "manual"])
    p_start.add_argument("--scope-org-id", default=None)
    p_start.add_argument("--triggered-by-user-id", default=None)

    p_finish = sub.add_parser("finish-task")
    p_finish.add_argument("task_id")
    p_finish.add_argument("--status", required=True, choices=["completed", "failed"])
    p_finish.add_argument("--bundle-path", default=None)
    p_finish.add_argument("--uploads-size-bytes", type=int, default=None)
    p_finish.add_argument("--error", default=None)

    args = parser.parse_args()

    if args.cmd == "get-schedule":
        asyncio.run(_get_schedule())
    elif args.cmd == "should-run":
        asyncio.run(_should_run())
    elif args.cmd == "mark-bundle-deleted":
        asyncio.run(_mark_bundle_deleted(args.bundle, args.reason))
    elif args.cmd == "has-run-today":
        asyncio.run(_has_run_today())
    elif args.cmd == "start-task":
        try:
            org = str(uuid.UUID(args.scope_org_id)) if args.scope_org_id else None
        except ValueError:
            print(f"Invalid --scope-org-id: {args.scope_org_id}", file=sys.stderr)
            sys.exit(1)
        asyncio.run(_start_task(args.type, args.triggered_by, org, args.triggered_by_user_id))
    elif args.cmd == "finish-task":
        asyncio.run(_finish_task(args.task_id, args.status, args.bundle_path,
                                  args.uploads_size_bytes, args.error))
    elif args.cmd == "table-counts":
        asyncio.run(_table_counts())
    elif args.cmd == "update-progress":
        asyncio.run(_update_progress(args.task_id, args.stage, args.current, args.total, args.message))
    elif args.cmd == "mark-stage-done":
        asyncio.run(_mark_stage_done(args.task_id, args.stage, args.count))


if __name__ == "__main__":
    main()
