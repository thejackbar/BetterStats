"""Pipeline target gauge — small FastAPI proxy + static page for a Twenty CRM
dashboard iFrame widget.

Serves one API endpoint (``GET /api/pipeline``) that sums open Opportunity
amounts from Twenty and compares them to a configurable target, and the
gauge page itself at ``/``. The Twenty API key never leaves this process —
the browser only ever talks to this app's own ``/api/pipeline``.

Twenty request/response shapes below are not guessed from public docs (Twenty's
docs site does not publish them — the schema is workspace-generated and only
shown in your own instance's Settings -> API & Webhooks playground). They are
taken from this repo's own working Twenty integration
(``backend/app/services/twenty_client.py``), verified against the live
instance: CURRENCY fields are ``{"amountMicros": int, "currencyCode": str}``,
list responses are ``{"data": {"<plural>": [...]}, "pageInfo": {"hasNextPage",
"endCursor"}}``, and the next page is requested with ``starting_after``.
"""
from __future__ import annotations

import asyncio
import datetime
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse

TWENTY_BASE_URL = os.environ.get("TWENTY_BASE_URL", "https://twenty.betterat.cricket").rstrip("/")
TWENTY_API_KEY = os.environ.get("TWENTY_API_KEY", "")
TARGET_AMOUNT = float(os.environ.get("TARGET_AMOUNT", "80000"))
CURRENCY_SYMBOL = os.environ.get("CURRENCY_SYMBOL", "$")
# Not in the original config list, but the API contract below needs an ISO code
# distinct from the display symbol above (see README "Deviations from the brief").
CURRENCY_CODE = os.environ.get("CURRENCY_CODE", "AUD")
# Default tuned to this exact workspace's real pipeline stage value (confirmed
# in backend/app/services/twenty_sync.py), not the generic placeholder "LOST".
EXCLUDED_STAGES = {
    s.strip().lower()
    for s in os.environ.get("EXCLUDED_STAGES", "Lost / Dormant").split(",")
    if s.strip()
}
ALLOWED_FRAME_ANCESTORS = os.environ.get("ALLOWED_FRAME_ANCESTORS", "").split()

CACHE_TTL_SECONDS = 60
MAX_PAGES = 200  # safety cap; a page is 60 records so this covers 12k opportunities

STATIC_DIR = Path(__file__).parent
_cache_lock = asyncio.Lock()
_cache: dict = {"current": None, "fetched_at": 0.0, "fetched_at_iso": None}


class TwentyFetchError(Exception):
    pass


async def _fetch_open_opportunities_total(http: httpx.AsyncClient) -> float:
    """Sum ``amount.amountMicros`` for every Opportunity whose ``stage`` is not
    in EXCLUDED_STAGES, in dollars. Paginates via ``pageInfo.endCursor`` /
    ``starting_after`` until ``hasNextPage`` is false."""
    headers = {"Authorization": f"Bearer {TWENTY_API_KEY}"}
    total_micros = 0
    cursor = None
    for _ in range(MAX_PAGES):
        params = {"limit": 60}
        if cursor:
            params["starting_after"] = cursor
        resp = await http.get(f"{TWENTY_BASE_URL}/rest/opportunities", headers=headers,
                               params=params, timeout=15)
        if resp.status_code >= 400:
            raise TwentyFetchError(f"GET /rest/opportunities -> {resp.status_code}: {resp.text[:200]}")
        payload = resp.json()
        data = (payload or {}).get("data") or {}
        opportunities = data.get("opportunities") or []
        for opp in opportunities:
            stage = (opp.get("stage") or "").strip().lower()
            if stage in EXCLUDED_STAGES:
                continue
            amount = opp.get("amount") or {}
            total_micros += amount.get("amountMicros") or 0
        page_info = (payload or {}).get("pageInfo") or {}
        cursor = page_info.get("endCursor")
        if page_info.get("hasNextPage") is not True or not cursor:
            break
    return total_micros / 1_000_000


async def _get_current_total(http: httpx.AsyncClient) -> float:
    """60s in-memory cache around the Twenty fetch, so dashboard auto-refresh
    (every 60s, possibly from several viewers) doesn't hammer the API."""
    async with _cache_lock:
        now = time.monotonic()
        if _cache["current"] is not None and now - _cache["fetched_at"] < CACHE_TTL_SECONDS:
            return _cache["current"]
        total = await _fetch_open_opportunities_total(http)
        _cache["current"] = total
        _cache["fetched_at"] = now
        _cache["fetched_at_iso"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return total


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as http:
        app.state.http = http
        yield


app = FastAPI(lifespan=lifespan)


@app.middleware("http")
async def frame_ancestors_csp(request: Request, call_next):
    response = await call_next(request)
    ancestors = " ".join(["'self'"] + ALLOWED_FRAME_ANCESTORS) if ALLOWED_FRAME_ANCESTORS else "'self'"
    response.headers["Content-Security-Policy"] = f"frame-ancestors {ancestors}"
    if "x-frame-options" in response.headers:
        del response.headers["x-frame-options"]
    return response


@app.get("/api/pipeline")
async def pipeline(request: Request):
    target = TARGET_AMOUNT
    target_param = request.query_params.get("target")
    if target_param:
        try:
            target = float(target_param)
        except ValueError:
            pass
    try:
        current = await _get_current_total(request.app.state.http)
    except (TwentyFetchError, httpx.HTTPError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return {
        "current": current,
        "target": target,
        "currency": CURRENCY_CODE,
        "currencySymbol": CURRENCY_SYMBOL,
        "updatedAt": _cache["fetched_at_iso"],
    }


@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")
