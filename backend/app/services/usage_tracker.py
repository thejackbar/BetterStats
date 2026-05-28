"""Usage breadcrumbs — fire-and-forget event recorder.

Drops a row into `usage_events` for every interesting API call and SPA
page view so we can see what features people actually use. Deliberately
silent on failure — tracking must never break a real request.

The middleware in app.main captures the API side; the frontend POSTs to
`/usage/event` for marketing + in-app route changes (which don't hit
their own backend endpoint).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Optional

from sqlalchemy import text

from app.models.db import async_session_maker

logger = logging.getLogger(__name__)


def hash_ip(ip: Optional[str]) -> Optional[str]:
    """Truncated SHA-256 of the client IP so the row isn't directly identifying."""
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


async def record_event(
    *,
    event_type: str,
    method: str,
    path: str,
    route: Optional[str] = None,
    status: int = 0,
    duration_ms: Optional[int] = None,
    user_id: Optional[str] = None,
    org_id: Optional[str] = None,
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert one breadcrumb. Opens its own session so it can run after the
    request session has been closed. Never raises."""
    try:
        async with async_session_maker() as session:
            await session.execute(
                text(
                    """
                    INSERT INTO usage_events (
                        event_type, method, path, route, status, duration_ms,
                        user_id, org_id, ip_hash, user_agent, referer, metadata
                    ) VALUES (
                        :event_type, :method, :path, :route, :status, :duration_ms,
                        :user_id, :org_id, :ip_hash, :user_agent, :referer,
                        CAST(:metadata AS JSONB)
                    )
                    """
                ),
                {
                    "event_type": event_type,
                    "method": method,
                    "path": path[:500] if path else "",
                    "route": route[:200] if route else None,
                    "status": int(status or 0),
                    "duration_ms": int(duration_ms) if duration_ms is not None else None,
                    "user_id": str(user_id) if user_id else None,
                    "org_id": str(org_id) if org_id else None,
                    "ip_hash": hash_ip(ip),
                    "user_agent": (user_agent or "")[:300] or None,
                    "referer": (referer or "")[:500] or None,
                    "metadata": json.dumps(metadata or {}),
                },
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: record_event failed ({e})")


def record_event_bg(**kwargs) -> None:
    """Schedule record_event on the running loop without awaiting it.

    Use from middleware so the request response isn't blocked on the DB
    write. The reference is dropped immediately — we don't care about the
    result.
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(record_event(**kwargs))
