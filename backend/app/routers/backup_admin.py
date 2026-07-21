"""Super Admin — Backups page.

Read-only for now (list of backup/restore tasks + current DB size stats).
Tasks are written by ``app/scripts/backup_task.py``, called from the host
backup/restore scripts (``ops/backup/``) — not from here. A "run backup now" /
"restore" trigger button is a later phase, once the backup-agent service that
gives the backend a safe way to reach the host's Docker/filesystem exists;
this router only reads what those scripts have already recorded.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
