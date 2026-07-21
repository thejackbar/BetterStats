"""Super Admin — Backups page.

Lists backup/restore tasks + current DB size stats (both written/computed
elsewhere — ``app/scripts/backup_task.py`` from the host scripts in
``ops/backup/``, ``services/backup_stats.py`` for the live size snapshot) and
exposes ONE write action: "run a backup now". That action proxies to the
``betterstats-backup-agent`` sidecar (see ops/backup/agent/) rather than
doing anything itself — this process has no Docker socket or host filesystem
access, by design, so it can't run backup.sh directly.

Restore is deliberately NOT triggerable from here, at all — full or per-club,
it stays an SSH-to-the-box operation (``ops/backup/restore.sh``). Restoring
needs the age PRIVATE key, which docs/backup-system.md says to keep OFFLINE;
exposing it to a network-reachable agent would defeat that.
"""
from __future__ import annotations

from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services import backup_stats

router = APIRouter(prefix="/club-admin/super/backups", tags=["backup-admin"])


@router.get("")
async def list_backup_tasks(
    task_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Requested/running/completed/failed backup + restore tasks, newest
    first, with the size/row-count snapshot stamped at completion time."""
    where = []
    params: dict = {"limit": limit, "offset": offset}
    if task_type:
        where.append("t.task_type = :task_type")
        params["task_type"] = task_type
    if status:
        where.append("t.status = :status")
        params["status"] = status
    where_clause = f"WHERE {' AND '.join(where)}" if where else ""

    rows = (await db.execute(text(f"""
        SELECT t.id, t.task_type, t.status, t.scope_org_id, o.name AS scope_org_name,
               t.triggered_by, t.triggered_by_user_id, t.bundle_path, t.bundle_timestamp,
               t.started_at, t.completed_at, t.db_size_bytes, t.uploads_size_bytes,
               t.total_row_count, t.club_stats, t.error_message
        FROM backup_tasks t
        LEFT JOIN organisations o ON o.id = t.scope_org_id
        {where_clause}
        ORDER BY t.started_at DESC
        LIMIT :limit OFFSET :offset
    """), params)).mappings().all()

    total = (await db.execute(
        text(f"SELECT COUNT(*) FROM backup_tasks t {where_clause}"), params
    )).scalar() or 0

    return {
        "tasks": [
            {
                "id": str(r["id"]),
                "task_type": r["task_type"],
                "status": r["status"],
                "scope_org_id": str(r["scope_org_id"]) if r["scope_org_id"] else None,
                "scope_org_name": r["scope_org_name"],
                "triggered_by": r["triggered_by"],
                "bundle_path": r["bundle_path"],
                "bundle_timestamp": r["bundle_timestamp"],
                "started_at": r["started_at"],
                "completed_at": r["completed_at"],
                "db_size_bytes": r["db_size_bytes"],
                "uploads_size_bytes": r["uploads_size_bytes"],
                "total_row_count": r["total_row_count"],
                "club_stats": r["club_stats"],
                "error_message": r["error_message"],
            }
            for r in rows
        ],
        "total": total,
    }


@router.get("/stats")
async def live_db_stats(
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Current (live, computed on request) total DB size and a per-club
    breakdown — not tied to any particular backup bundle. Per-club size is an
    estimate (see backup_stats module docstring); row counts are exact."""
    return await backup_stats.compute_db_stats(db)


@router.post("/run")
async def run_backup_now(
    user: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Kicks off an immediate backup via the backup-agent sidecar. Fire-and-
    forget: the agent starts backup.sh in the background and returns right
    away — poll the task list (GET /club-admin/super/backups) for progress,
    same as a scheduled run. 503s with a clear message if the agent isn't
    configured/reachable rather than hanging on a request that can take
    minutes."""
    if not settings.backup_agent_url:
        raise HTTPException(
            status_code=503,
            detail="The backup agent isn't configured on this server yet "
                   "(BACKUP_AGENT_URL unset) — see docs/backup-system.md. "
                   "Run a backup manually on the server in the meantime: "
                   "ops/backup/backup.sh",
        )
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"{settings.backup_agent_url.rstrip('/')}/run-backup",
                headers={"X-Agent-Secret": settings.backup_agent_secret},
                json={"triggered_by_user_id": str(user.id)},
            )
        resp.raise_for_status()
        return resp.json()
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=502, detail=f"Backup agent returned {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Could not reach the backup agent: {e}")
