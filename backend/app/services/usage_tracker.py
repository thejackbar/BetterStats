"""Usage breadcrumbs — fire-and-forget event recorder.

Drops a row into `usage_events` for every interesting API call and SPA
page view so we can see what features people actually use. Deliberately
silent on failure — tracking must never break a real request.

Geo enrichment:
  - Country comes from Cloudflare's `cf-ipcountry` header (free on every
    CF plan) — captured by the caller and passed in at insert time.
  - City + region come from a follow-up ip-api.com lookup (free, no key,
    45 req/min/IP) cached in-process by IP hash. The lookup runs after
    the row is written and UPDATEs the row in place. We never store the
    raw IP — only the city/region resolved from it.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Optional

import httpx
from sqlalchemy import text

from app.models.db import async_session_maker

logger = logging.getLogger(__name__)

# In-process cache of ip_hash -> {country, region, city, queried_at}.
# Avoids hammering ip-api.com when the same person clicks 50 things.
# Bounded by a soft cap; oldest entries are evicted when we go over.
_GEO_CACHE: dict[str, dict] = {}
_GEO_CACHE_CAP = 5000
_GEO_LOOKUP_TIMEOUT = 3.0
# Country codes that we don't bother enriching beyond the CF header
# (private/loopback markers Cloudflare uses).
_GEO_SKIP_COUNTRIES = {"XX", "T1"}


def hash_ip(ip: Optional[str]) -> Optional[str]:
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
    country: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Insert one breadcrumb. Opens its own session so it can run after the
    request session has been closed. Never raises."""
    ip_h = hash_ip(ip)
    region = None
    city = None
    # Cached city/region for this IP, if we've already looked it up.
    cached = _GEO_CACHE.get(ip_h) if ip_h else None
    if cached:
        country = country or cached.get("country")
        region = cached.get("region")
        city = cached.get("city")

    try:
        async with async_session_maker() as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO usage_events (
                        event_type, method, path, route, status, duration_ms,
                        user_id, org_id, ip_hash, user_agent, referer,
                        country, region, city, metadata
                    ) VALUES (
                        :event_type, :method, :path, :route, :status, :duration_ms,
                        :user_id, :org_id, :ip_hash, :user_agent, :referer,
                        :country, :region, :city,
                        CAST(:metadata AS JSONB)
                    )
                    RETURNING id
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
                    "ip_hash": ip_h,
                    "user_agent": (user_agent or "")[:300] or None,
                    "referer": (referer or "")[:500] or None,
                    "country": (country or "").upper()[:2] or None,
                    "region": (region or "")[:80] or None,
                    "city": (city or "")[:80] or None,
                    "metadata": json.dumps(metadata or {}),
                },
            )
            row_id = result.scalar()
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: record_event failed ({e})")
        return

    # Schedule a follow-up city/region lookup if we have an IP, haven't
    # cached it yet, and the country isn't a private marker. Updates the
    # row we just wrote.
    if ip and ip_h and row_id and not cached and (country or "").upper() not in _GEO_SKIP_COUNTRIES:
        try:
            asyncio.get_running_loop().create_task(
                _enrich_geo(ip=ip, ip_hash=ip_h, row_id=row_id, country=country)
            )
        except RuntimeError:
            pass


async def _enrich_geo(*, ip: str, ip_hash: str, row_id: int, country: Optional[str]) -> None:
    """Look up city/region via ip-api.com, cache, and UPDATE the row.

    ip-api.com free tier: 45 req/min/IP, no key, JSON. Their TOS allows
    non-commercial use. Endpoint: http://ip-api.com/json/{ip}.
    """
    try:
        async with httpx.AsyncClient(timeout=_GEO_LOOKUP_TIMEOUT) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,regionName,city"},
            )
            if resp.status_code != 200:
                _GEO_CACHE[ip_hash] = {"country": country, "region": None, "city": None}
                return
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: geo lookup failed for {ip_hash}: {e}")
        _GEO_CACHE[ip_hash] = {"country": country, "region": None, "city": None}
        return

    if data.get("status") != "success":
        _GEO_CACHE[ip_hash] = {"country": country, "region": None, "city": None}
        return

    cc = (data.get("countryCode") or country or "").upper()[:2] or None
    region = data.get("regionName") or None
    city = data.get("city") or None

    # Soft-bound the cache.
    if len(_GEO_CACHE) >= _GEO_CACHE_CAP:
        # Drop ~10% of the oldest entries by simple FIFO order.
        for k in list(_GEO_CACHE.keys())[: _GEO_CACHE_CAP // 10]:
            _GEO_CACHE.pop(k, None)
    _GEO_CACHE[ip_hash] = {"country": cc, "region": region, "city": city}

    try:
        async with async_session_maker() as session:
            # Backfill this row plus any other rows with the same IP hash
            # that landed before the lookup finished — they all share
            # location.
            await session.execute(
                text(
                    """
                    UPDATE usage_events
                    SET country = COALESCE(:country, country),
                        region  = COALESCE(:region,  region),
                        city    = COALESCE(:city,    city)
                    WHERE ip_hash = :ip_hash
                      AND (region IS NULL OR city IS NULL)
                    """
                ),
                {"country": cc, "region": region, "city": city, "ip_hash": ip_hash},
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: geo backfill update failed: {e}")


def record_event_bg(**kwargs) -> None:
    """Schedule record_event without awaiting it."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    loop.create_task(record_event(**kwargs))
