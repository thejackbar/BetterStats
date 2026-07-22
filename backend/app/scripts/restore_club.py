"""CLI used by ops/backup/restore.sh's `restore-club` command.

Runs from inside the betterstats-backend container, where it can reach both
the live app DB (async_session_maker, as usual) and the scratch Postgres
container restore.sh already spun up and pg_restore'd the chosen bundle into
(reachable by container name on the same Docker network).

Usage (normally invoked BY restore.sh, not run by hand):
  # dry run — report only, no write, safe to run repeatedly
  python -m app.scripts.restore_club <org_id> --scratch-dsn postgresql+asyncpg://user:pass@betterstats-restore-scratch:5432/betterstats

  # the real, destructive restore (snapshots current live rows first)
  python -m app.scripts.restore_club <org_id> --scratch-dsn ... --apply

  # undo a previous --apply run
  python -m app.scripts.restore_club --rollback /mnt/media/bettercricket/backup/club-restores/<task_id>.json
"""
import argparse
import asyncio
import json
import sys

from app.models.db import async_session_maker
from app.services import club_restore


async def _run(org_id: str, scratch_dsn: str, apply: bool, task_id: str, snapshot_dir: str):
    async with async_session_maker() as session:
        summary = await club_restore.plan_and_run_club_restore(
            live_session=session, scratch_dsn=scratch_dsn, org_id=org_id,
            task_id=task_id, snapshot_dir=snapshot_dir, apply=apply,
        )
    print(json.dumps(summary, default=str, indent=2))


async def _rollback(snapshot_path: str):
    async with async_session_maker() as session:
        result = await club_restore.rollback_club_restore(live_session=session, snapshot_path=snapshot_path)
    print(json.dumps(result, default=str, indent=2))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("org_id", nargs="?", help="Organisation to restore (omit with --rollback)")
    parser.add_argument("--scratch-dsn", help="asyncpg DSN for the scratch Postgres holding the restored bundle")
    parser.add_argument("--apply", action="store_true", help="Actually write (default is dry-run/report-only)")
    parser.add_argument("--task-id", default="manual", help="backup_tasks.id this run is logged against")
    parser.add_argument("--snapshot-dir", default="/mnt/media/bettercricket/backup/club-restores")
    parser.add_argument("--rollback", metavar="SNAPSHOT_JSON", help="Undo a previous --apply run from its snapshot file")
    args = parser.parse_args()

    if args.rollback:
        asyncio.run(_rollback(args.rollback))
        return

    if not args.org_id or not args.scratch_dsn:
        print("org_id and --scratch-dsn are required unless using --rollback", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_run(args.org_id, args.scratch_dsn, args.apply, args.task_id, args.snapshot_dir))


if __name__ == "__main__":
    main()
