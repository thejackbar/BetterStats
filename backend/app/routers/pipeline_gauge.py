"""Pipeline target gauge — a small superadmin-only widget for a Twenty CRM
dashboard iFrame, folded into the main backend so it needs no separate
service, container, or API key: it reuses the Twenty credentials
(``settings.twenty_api_url`` / ``twenty_api_key``) already configured for the
live twenty_sync integration (see ``services/twenty_client.py``).

Two routes, both gated by HTTP Basic Auth (``GAUGE_USERNAME`` /
``GAUGE_PASSWORD`` — this widget has no user accounts of its own, so it's one
shared credential handed only to superadmins, not tied to BetterStats' or
Twenty's own logins):
  - ``GET /public/gauge/`` — the gauge HTML page.
  - ``GET /public/gauge/pipeline`` — the JSON `{current, target, currency,
    currencySymbol, updatedAt}` the page fetches.

Twenty request/response shapes (CURRENCY = ``{"amountMicros", "currencyCode"}``,
list responses = ``{"data": {"opportunities": [...]}, "pageInfo":
{"hasNextPage", "endCursor"}}``, next page via ``starting_after``) are taken
from this repo's own verified integration (``twenty_client.py``), not guessed
from Twenty's public docs, which don't publish them.
"""
from __future__ import annotations

import asyncio
import datetime
import secrets
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.config.settings import settings

router = APIRouter(prefix="/public/gauge", tags=["public-gauge"])

# Plain constants, not Settings fields — deliberately, to keep the deployment
# surface to just the two auth env vars below. Edit these directly in code if
# the target/currency/excluded stages ever need to change.
TARGET_AMOUNT = 80000.0
CURRENCY_SYMBOL = "$"
CURRENCY_CODE = "AUD"
# This workspace's real Opportunity pipeline stage to exclude (see
# docs/twenty-crm-integration.md section 3.4) — not a generic "LOST" value.
EXCLUDED_STAGES = {"lost / dormant"}
ALLOWED_FRAME_ANCESTORS = "https://twenty.betterat.cricket"

CACHE_TTL_SECONDS = 60
MAX_PAGES = 200  # safety cap; a page is 60 records so this covers 12k opportunities

_cache_lock = asyncio.Lock()
_cache: dict = {"current": None, "fetched_at": 0.0, "fetched_at_iso": None}

_basic_auth = HTTPBasic()


def _require_superadmin(credentials: HTTPBasicCredentials = Depends(_basic_auth)) -> None:
    """Fails closed: an unset GAUGE_PASSWORD rejects every request rather than
    silently leaving the page open. Constant-time comparison on both fields."""
    if not settings.gauge_username or not settings.gauge_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GAUGE_USERNAME/GAUGE_PASSWORD not configured",
        )
    user_ok = secrets.compare_digest(credentials.username, settings.gauge_username)
    pass_ok = secrets.compare_digest(credentials.password, settings.gauge_password)
    if not (user_ok and pass_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )


class TwentyFetchError(Exception):
    pass


async def _fetch_open_opportunities_total() -> float:
    """Sum ``amount.amountMicros`` for every Opportunity whose ``stage`` is not
    in EXCLUDED_STAGES, in dollars. Paginates via ``pageInfo.endCursor`` /
    ``starting_after`` until ``hasNextPage`` is false."""
    base = settings.twenty_api_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.twenty_api_key}"}
    total_micros = 0
    cursor = None
    async with httpx.AsyncClient() as http:
        for _ in range(MAX_PAGES):
            params = {"limit": 60}
            if cursor:
                params["starting_after"] = cursor
            resp = await http.get(f"{base}/rest/opportunities", headers=headers,
                                   params=params, timeout=15)
            if resp.status_code >= 400:
                raise TwentyFetchError(
                    f"GET /rest/opportunities -> {resp.status_code}: {resp.text[:200]}")
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


async def _get_current_total() -> float:
    """60s in-memory cache around the Twenty fetch, so dashboard auto-refresh
    (every 60s, possibly from several viewers) doesn't hammer the API."""
    async with _cache_lock:
        now = time.monotonic()
        if _cache["current"] is not None and now - _cache["fetched_at"] < CACHE_TTL_SECONDS:
            return _cache["current"]
        total = await _fetch_open_opportunities_total()
        _cache["current"] = total
        _cache["fetched_at"] = now
        _cache["fetched_at_iso"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        return total


@router.get("/pipeline", dependencies=[Depends(_require_superadmin)])
async def pipeline(request: Request):
    if not settings.twenty_configured:
        return JSONResponse(status_code=502, content={"error": "Twenty is not configured"})
    target = TARGET_AMOUNT
    target_param = request.query_params.get("target")
    if target_param:
        try:
            target = float(target_param)
        except ValueError:
            pass
    try:
        current = await _get_current_total()
    except (TwentyFetchError, httpx.HTTPError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return {
        "current": current,
        "target": target,
        "currency": CURRENCY_CODE,
        "currencySymbol": CURRENCY_SYMBOL,
        "updatedAt": _cache["fetched_at_iso"],
    }


_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Pipeline Target</title>
<style>
  :root {
    color-scheme: dark;
    --bg: #111318;
    --fg: #e8e9ec;
    --muted: #8a8f98;
    --track: #262a33;
    --red: #e5484d;
    --amber: #f5a623;
    --green: #3fb950;
  }
  * { box-sizing: border-box; }
  html, body {
    height: 100%;
    margin: 0;
    background: var(--bg);
    color: var(--fg);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  }
  body {
    display: flex;
    align-items: center;
    justify-content: center;
    padding: clamp(8px, 3vw, 24px);
  }
  .card {
    width: 100%;
    max-width: 440px;
    display: flex;
    flex-direction: column;
    align-items: center;
  }
  .gauge-wrap { position: relative; width: 100%; }
  svg { display: block; width: 100%; height: auto; }
  .track { fill: none; stroke: var(--track); stroke-linecap: round; }
  .fill { fill: none; stroke-linecap: round; transition: stroke-dasharray 0.6s ease, stroke 0.6s ease; }
  .center-text {
    position: absolute;
    left: 0; right: 0;
    top: 58%;
    display: flex;
    flex-direction: column;
    align-items: center;
    text-align: center;
  }
  .current { font-size: clamp(1.4rem, 8vw, 2.6rem); font-weight: 650; line-height: 1; letter-spacing: -0.02em; }
  .sub { margin-top: 6px; font-size: clamp(0.7rem, 2.6vw, 0.9rem); color: var(--muted); }
  .error { margin-top: 6px; font-size: 0.8rem; color: var(--red); }
</style>
</head>
<body>
  <div class="card">
    <div class="gauge-wrap">
      <svg viewBox="0 0 200 120" preserveAspectRatio="xMidYMid meet">
        <path class="track" d="" stroke-width="14" id="track"></path>
        <path class="fill" d="" stroke-width="14" id="fill"></path>
      </svg>
      <div class="center-text">
        <div class="current" id="current">&nbsp;</div>
        <div class="sub" id="sub">Loading…</div>
      </div>
    </div>
  </div>

<script>
(function () {
  const CX = 100, CY = 100, R = 82;

  function arcPoint(angleDeg) {
    const rad = (Math.PI / 180) * angleDeg;
    return [CX + R * Math.cos(rad), CY - R * Math.sin(rad)];
  }

  function describeArc(startDeg, endDeg) {
    const [x1, y1] = arcPoint(startDeg);
    const [x2, y2] = arcPoint(endDeg);
    const largeArc = Math.abs(startDeg - endDeg) > 180 ? 1 : 0;
    return `M ${x1} ${y1} A ${R} ${R} 0 ${largeArc} 1 ${x2} ${y2}`;
  }

  const trackEl = document.getElementById("track");
  const fillEl = document.getElementById("fill");
  const currentEl = document.getElementById("current");
  const subEl = document.getElementById("sub");

  trackEl.setAttribute("d", describeArc(180, 0));

  function colourFor(pct) {
    if (pct < 33) return "var(--red)";
    if (pct < 66) return "var(--amber)";
    return "var(--green)";
  }

  function formatMoney(symbol, amount) {
    return symbol + Math.round(amount).toLocaleString("en-AU");
  }

  function render(data) {
    const symbol = data.currencySymbol || "$";
    const current = Number(data.current) || 0;
    const target = Number(data.target) || 0;
    const pct = target > 0 ? (current / target) * 100 : 0;
    const clampedPct = Math.max(0, Math.min(100, pct));

    const endAngle = 180 - (clampedPct / 100) * 180;
    fillEl.setAttribute("d", describeArc(180, endAngle));
    fillEl.setAttribute("stroke", colourFor(pct));

    currentEl.textContent = formatMoney(symbol, current);
    subEl.textContent = `${pct.toFixed(1)}% of ${formatMoney(symbol, target)}`;
  }

  function targetOverride() {
    return new URLSearchParams(window.location.search).get("target");
  }

  async function load() {
    try {
      let url = "pipeline";
      const override = targetOverride();
      if (override) url += "?target=" + encodeURIComponent(override);
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      render(await resp.json());
    } catch (err) {
      subEl.textContent = "Couldn't load pipeline data";
      subEl.classList.add("error");
    }
  }

  load();
  setInterval(load, 60000);
})();
</script>
</body>
</html>
"""


@router.get("/", dependencies=[Depends(_require_superadmin)], response_class=HTMLResponse)
async def gauge_page():
    return HTMLResponse(
        content=_PAGE_HTML,
        headers={"Content-Security-Policy": f"frame-ancestors 'self' {ALLOWED_FRAME_ANCESTORS}"},
    )
