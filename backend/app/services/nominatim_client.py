"""OpenStreetMap Nominatim — free suburb boundary lookup.

There's no bundled Australian postcode-boundary dataset in this app (the
real thing is an ABS shapefile release, not something worth vendoring for
one admin map). Nominatim's `/search` endpoint, queried by suburb name
rather than by postcode, often returns a real `boundary`/`administrative`
polygon for the suburb — Australian postcodes themselves are only ever
mapped as a point in OSM, but most postcodes map onto a single named
suburb, so the suburb boundary is a reasonable free stand-in for "the
postcode area".

Nominatim's usage policy caps free use at ~1 request/second and requires a
descriptive User-Agent. A lookup only happens once per club (the caller
persists the result to `marketing_clubs.boundary_geojson` and never
re-fetches), and MIN_INTERVAL below holds the rate even when several
uncached clubs are opened in a row.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://nominatim.openstreetmap.org/search"
TIMEOUT = 15.0
# Nominatim's usage policy is one request a second, and going over it gets an
# IP blocked rather than throttled. A rep clicking down the queue can now fire
# these back to back (the Sales Workspace drawer fetches a boundary lazily, so
# they are no longer paced by how fast a pane can load), so the gap is kept
# here rather than left to whoever calls. This only ever delays a club whose
# polygon has never been cached, and never anything a person is waiting on.
MIN_INTERVAL = 1.1
_lock = asyncio.Lock()
_last_call = 0.0
_HEADERS = {
    "User-Agent": "BetterCricket/1.0 (support@bettersports.com.au)",
    "Accept": "application/json",
}


async def find_suburb_boundary(suburb: str, state: Optional[str], country: str = "Australia") -> Optional[dict]:
    """Best-effort lookup of a suburb's admin boundary polygon.

    Returns the raw GeoJSON geometry (Polygon or MultiPolygon) of the best
    `boundary`/`administrative` match, or None if nothing suitable was found
    (a plain Point result, no match, or a request failure) — never raises.
    """
    if not suburb:
        return None
    q = ", ".join(p for p in [suburb, state, country] if p)
    params = {
        "q": q,
        "format": "jsonv2",
        "polygon_geojson": 1,
        "addressdetails": 1,
        "limit": 5,
    }
    try:
        async with _lock:
            global _last_call
            wait = MIN_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            async with httpx.AsyncClient(timeout=TIMEOUT) as client:
                r = await client.get(BASE_URL, params=params, headers=_HEADERS)
            _last_call = time.monotonic()
            if r.status_code != 200:
                logger.debug(f"Nominatim: search {q!r} -> {r.status_code}")
                return None
            results = r.json()
    except Exception as e:
        logger.warning(f"Nominatim: search {q!r} failed: {e}")
        return None

    # Prefer a real admin-boundary polygon over a plain point/address match.
    for res in results:
        if res.get("category") == "boundary" and res.get("type") == "administrative":
            geo = res.get("geojson")
            if geo and geo.get("type") in ("Polygon", "MultiPolygon"):
                return geo
    # Fall back to the first result that's at least a polygon of some kind.
    for res in results:
        geo = res.get("geojson")
        if geo and geo.get("type") in ("Polygon", "MultiPolygon"):
            return geo
    return None
