"""CLI used by the host backup/restore scripts (ops/backup/backup.sh,
ops/backup/restore.sh) to read the configured schedule and to log each run
into ``backup_tasks``. Invoked via ``docker compose exec -T
betterstats-backend python -m app.scripts.backup_task ...`` — this is how a
host-level shell script (no app import, no DB driver of its own) gets at the
app's own Postgres session and the backup_stats snapshot logic.

Usage:
  # prints "HOUR MINUTE RETENTION_DAYS" (space-separated, easy for bash to
  # `read` into three variables)
  python -m app.scripts.backup_task get-schedule

  # creates a backup_tasks row, prints its id (only the id, to stdout)
  python -m app.scripts.backup_task start-task --type backup --triggered-by scheduled
  python -m app.scripts.backup_task start-task --type restore_full --triggered-by manual

  # marks a task completed, stamping the current DB/per-club stats plus
  # whatever the shell script measured on disk
  python -m app.scripts.backup_task finish-task <task_id> --status completed \\
      --bundle-path /srv/backups/betterstats/2026-07-21T03-00-00Z --uploads-size-bytes 12345

  # marks a task failed
  python -m app.scripts.backup_task finish-task <task_id> --status failed --error "pg_dump exited 1"

  # prints "1" (has an already-completed backup task started today) or "0" —
  # lets the timer's frequent tick skip re-running once today's backup is done
  python -m app.scripts.backup_task has-run-today
"""
import argparse
import asyncio
import json
import sys
import uuid

from sqlalchemy import text

from app.models.db import async_session_maker
from app.services import backup_stats, platform_settings as ps


async def _get_schedule():
    async with async_session_maker() as session:
        sched = await ps.get_backup_schedule(session)
    print(f"{sched['hour']} {sched['minute']} {sched['retention_days']}")


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
    async with async_session_maker() as session:
        row = (await session.execute(text(
            "SELECT 1 FROM backup_tasks WHERE task_type = 'backup' AND status = 'completed' "
            "AND started_at::date = NOW()::date LIMIT 1"
        ))).first()
        print("1" if row else "0")


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("get-schedule")
    sub.add_parser("has-run-today")

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


if __name__ == "__main__":
    main()
