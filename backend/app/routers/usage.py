"""Usage breadcrumbs — endpoints.

- POST /usage/event: public beacon for frontend SPA route changes.
  Marketing pages, public yearbooks, in-app routes — everything the
  user sees that doesn't naturally hit its own API.
- GET /club-admin/usage/recent: super-admin only — latest events.
- GET /club-admin/usage/top-routes: super-admin only — aggregated
  counts over a window.
- GET /club-admin/usage/top-users: super-admin only — most active
  users over a window.

API-call events come from the middleware in app.main; the beacon writes
the page-view events.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import User, get_db
from app.routers.auth import require_super_admin
from app.services.usage_tracker import record_event

router = APIRouter(tags=["usage"])


class PageViewIn(BaseModel):
    path: str
    referer: Optional[str] = None
    # Optional human-meaningful name e.g. "ClubDashboard", "YearbookPage"
    name: Optional[str] = None


@router.post("/usage/event")
async def post_event(payload: PageViewIn, request: Request):
    """Anonymous SPA page-view beacon. Always returns 204."""
    # Pull user_id from session cookie if present, but never required.
    from app.main import _decode_user_id, _client_ip  # local import to avoid cycle

    await record_event(
        event_type="page_view",
        method="GET",
        path=payload.path or "/",
        route=payload.name,
        status=200,
        user_id=_decode_user_id(request),
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        referer=payload.referer or request.headers.get("referer"),
    )
    return {"ok": True}


# ─── Super-admin views ───────────────────────────────────────────────────────

@router.get("/club-admin/usage/recent")
async def recent_events(
    limit: int = 200,
    event_type: Optional[str] = None,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    limit = max(1, min(limit, 1000))
    where = ""
    params: dict = {"lim": limit}
    if event_type:
        where = "WHERE ue.event_type = :etype"
        params["etype"] = event_type
    rows = await db.execute(
        text(
            f"""
            SELECT
                ue.id, ue.created_at, ue.event_type, ue.method, ue.path,
                ue.route, ue.status, ue.duration_ms, ue.user_id,
                ue.ip_hash, ue.referer,
                u.email AS user_email, u.display_name AS user_display_name
            FROM usage_events ue
            LEFT JOIN users u ON u.id = ue.user_id
            {where}
            ORDER BY ue.created_at DESC
            LIMIT :lim
            """
        ),
        params,
    )
    return [
        {
            "id": r["id"],
            "created_at": r["created_at"].isoformat() if r["created_at"] else None,
            "event_type": r["event_type"],
            "method": r["method"],
            "path": r["path"],
            "route": r["route"],
            "status": r["status"],
            "duration_ms": r["duration_ms"],
            "user_id": str(r["user_id"]) if r["user_id"] else None,
            "user_email": r["user_email"],
            "user_display_name": r["user_display_name"],
            "ip_hash": r["ip_hash"],
            "referer": r["referer"],
        }
        for r in rows.mappings().all()
    ]


@router.get("/club-admin/usage/top-routes")
async def top_routes(
    days: int = 7,
    limit: int = 30,
    event_type: Optional[str] = None,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 200))
    params: dict = {"days": days, "lim": limit}
    type_clause = ""
    if event_type:
        type_clause = "AND event_type = :etype"
        params["etype"] = event_type
    rows = await db.execute(
        text(
            f"""
            SELECT
                COALESCE(route, path) AS route_key,
                event_type,
                COUNT(*) AS hits,
                COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL) AS unique_users,
                COUNT(DISTINCT ip_hash) FILTER (WHERE ip_hash IS NOT NULL) AS unique_ips,
                MAX(created_at) AS last_hit
            FROM usage_events
            WHERE created_at >= NOW() - (:days * INTERVAL '1 day')
            {type_clause}
            GROUP BY route_key, event_type
            ORDER BY hits DESC
            LIMIT :lim
            """
        ),
        params,
    )
    return [
        {
            "route": r["route_key"],
            "event_type": r["event_type"],
            "hits": int(r["hits"] or 0),
            "unique_users": int(r["unique_users"] or 0),
            "unique_ips": int(r["unique_ips"] or 0),
            "last_hit": r["last_hit"].isoformat() if r["last_hit"] else None,
        }
        for r in rows.mappings().all()
    ]


@router.get("/club-admin/usage/top-users")
async def top_users(
    days: int = 7,
    limit: int = 30,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    days = max(1, min(days, 365))
    limit = max(1, min(limit, 200))
    rows = await db.execute(
        text(
            """
            SELECT
                ue.user_id,
                u.email AS user_email,
                u.display_name AS user_display_name,
                COUNT(*) AS hits,
                COUNT(DISTINCT COALESCE(ue.route, ue.path)) AS unique_routes,
                MAX(ue.created_at) AS last_hit
            FROM usage_events ue
            LEFT JOIN users u ON u.id = ue.user_id
            WHERE ue.created_at >= NOW() - (:days * INTERVAL '1 day')
              AND ue.user_id IS NOT NULL
            GROUP BY ue.user_id, u.email, u.display_name
            ORDER BY hits DESC
            LIMIT :lim
            """
        ),
        {"days": days, "lim": limit},
    )
    return [
        {
            "user_id": str(r["user_id"]) if r["user_id"] else None,
            "user_email": r["user_email"],
            "user_display_name": r["user_display_name"],
            "hits": int(r["hits"] or 0),
            "unique_routes": int(r["unique_routes"] or 0),
            "last_hit": r["last_hit"].isoformat() if r["last_hit"] else None,
        }
        for r in rows.mappings().all()
    ]


@router.get("/club-admin/usage/summary")
async def summary(
    days: int = 7,
    _: User = Depends(require_super_admin),
    db: AsyncSession = Depends(get_db),
):
    days = max(1, min(days, 365))
    row = await db.execute(
        text(
            """
            SELECT
                COUNT(*)                                                        AS total,
                COUNT(*) FILTER (WHERE event_type = 'api')                      AS api_hits,
                COUNT(*) FILTER (WHERE event_type = 'page_view')                AS page_views,
                COUNT(DISTINCT user_id) FILTER (WHERE user_id IS NOT NULL)      AS unique_users,
                COUNT(DISTINCT ip_hash) FILTER (WHERE ip_hash IS NOT NULL)      AS unique_ips
            FROM usage_events
            WHERE created_at >= NOW() - (:days * INTERVAL '1 day')
            """
        ),
        {"days": days},
    )
    r = row.mappings().first()
    return {
        "days": days,
        "total": int(r["total"] or 0),
        "api_hits": int(r["api_hits"] or 0),
        "page_views": int(r["page_views"] or 0),
        "unique_users": int(r["unique_users"] or 0),
        "unique_ips": int(r["unique_ips"] or 0),
    }
