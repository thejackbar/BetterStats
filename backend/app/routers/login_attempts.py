"""Super-admin view of the login-attempt audit log.

Reads the append-only ``login_attempts`` table (written by
``services.login_audit`` from the auth login handler). Platform-security data
with no single club context — a failed login for an unknown username has no org
— so it's gated to super admins, matching the usage-analytics endpoints.
"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text

from app.models.db import User, get_db
from app.routers.auth import require_super_admin

router = APIRouter(prefix="/club-admin", tags=["security"])


@router.get("/super/login-attempts")
async def list_login_attempts(
    limit: int = Query(200, ge=1, le=1000),
    only_failures: bool = Query(False),
    q: str | None = Query(None, description="Filter by attempted username/email (substring)"),
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    """Recent login attempts, newest first. Joins the resolved account/club when
    the attempted username matched a real user."""
    clauses: list[str] = []
    params: dict = {"limit": limit}
    if only_failures:
        clauses.append("la.success = false")
    if q and q.strip():
        clauses.append("la.username ILIKE :q")
        params["q"] = f"%{q.strip()}%"
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""

    rows = (await db.execute(text(f"""
        SELECT
            la.id, la.created_at, la.username, la.success, la.failure_reason,
            la.user_id, la.org_id, la.ip_hash, la.user_agent, la.country,
            u.display_name AS user_display_name,
            o.name AS org_name
        FROM login_attempts la
        LEFT JOIN users u ON u.id = la.user_id
        LEFT JOIN organisations o ON o.id = la.org_id
        {where}
        ORDER BY la.created_at DESC
        LIMIT :limit
    """), params)).mappings().all()

    return [
        {
            "id": r["id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "username": r["username"],
            "success": r["success"],
            "failure_reason": r["failure_reason"],
            "user_id": str(r["user_id"]) if r["user_id"] else None,
            "user_display_name": r["user_display_name"],
            "org_id": str(r["org_id"]) if r["org_id"] else None,
            "org_name": r["org_name"],
            "ip_hash": r["ip_hash"],
            "user_agent": r["user_agent"],
            "country": r["country"],
        }
        for r in rows
    ]
