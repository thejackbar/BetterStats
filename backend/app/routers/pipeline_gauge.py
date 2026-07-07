"""Dashboard gauges — small superadmin-only widgets for Twenty CRM dashboard
iFrames, folded into the main backend so they need no separate service,
container, or API key: they reuse the Twenty credentials
(``settings.twenty_api_url`` / ``twenty_api_key``) already configured for the
live twenty_sync integration (see ``services/twenty_client.py``).

Each gauge is one entry in GAUGES below (slug -> title/description/target/
stage-match function) and gets its own stable, addressable URL pair:
  - ``GET /public/gauge/{slug}/`` — the gauge HTML page.
  - ``GET /public/gauge/{slug}/data`` — the JSON `{current, target, currency,
    currencySymbol, updatedAt, title, desc}` the page fetches.

``GET /public/gauge/`` and ``GET /public/gauge/pipeline`` are kept as-is,
equivalent to the "won" slug — this is the URL already embedded in a live
Twenty dashboard widget, so it must keep working unchanged rather than move
to /public/gauge/won/.

All routes are gated by HTTP Basic Auth (``GAUGE_USERNAME`` / ``GAUGE_PASSWORD``
— these widgets have no user accounts of their own, so it's one shared
credential handed only to superadmins, not tied to BetterStats' or Twenty's
own logins).

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
# surface to just the two auth env vars below. Edit these directly in code
# (or add a new GAUGES entry) rather than growing the env-var surface.
CURRENCY_SYMBOL = "$"
CURRENCY_CODE = "AUD"
ALLOWED_FRAME_ANCESTORS = "https://twenty.betterat.cricket"

CACHE_TTL_SECONDS = 60
MAX_PAGES = 200  # safety cap; a page is 60 records so this covers 12k opportunities

# This workspace's real Opportunity pipeline stage value for a closed-won deal
# (see docs/twenty-crm-integration.md section 3.4).
_WON = "won"
_LOST_DORMANT = "lost / dormant"


def _match_won(stage: str) -> bool:
    return stage == _WON


def _match_projected(stage: str) -> bool:
    """Won + every open stage (Target/Contacted/Engaged/Trial/Proposal) — i.e.
    everything that could still land, excluding only Lost / Dormant. A simple
    best-case total, not a probability-weighted forecast (Twenty doesn't carry
    a per-stage win-rate here) — tell me if you want it weighted instead."""
    return stage != _LOST_DORMANT


# One entry per gauge widget. Add a new slug here to get a new
# /public/gauge/{slug}/ + /public/gauge/{slug}/data pair for free.
GAUGES = {
    "won": {
        "title": "Sales Budget",
        "desc": "Won revenue vs. target",
        "target": 80000.0,
        "match": _match_won,
    },
    "projected": {
        "title": "Projected Revenue",
        "desc": "Won + open pipeline vs. target",
        "target": 80000.0,
        "match": _match_projected,
    },
}

_cache_lock = asyncio.Lock()
_cache: dict[str, dict] = {}  # slug -> {"current", "fetched_at", "fetched_at_iso"}

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


async def _fetch_total(match) -> float:
    """Sum ``amount.amountMicros`` for every Opportunity whose ``stage``
    satisfies ``match(stage)``, in dollars. Paginates via ``pageInfo.endCursor``
    / ``starting_after`` until ``hasNextPage`` is false."""
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
                if not match(stage):
                    continue
                amount = opp.get("amount") or {}
                total_micros += amount.get("amountMicros") or 0
            page_info = (payload or {}).get("pageInfo") or {}
            cursor = page_info.get("endCursor")
            if page_info.get("hasNextPage") is not True or not cursor:
                break
    return total_micros / 1_000_000


async def _get_current_total(slug: str, match) -> float:
    """60s in-memory cache per gauge, so dashboard auto-refresh (every 60s,
    possibly from several viewers/widgets) doesn't hammer the API."""
    async with _cache_lock:
        now = time.monotonic()
        entry = _cache.get(slug)
        if entry is not None and now - entry["fetched_at"] < CACHE_TTL_SECONDS:
            return entry["current"]
        total = await _fetch_total(match)
        _cache[slug] = {
            "current": total,
            "fetched_at": now,
            "fetched_at_iso": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        return total


async def _gauge_data(slug: str, request: Request):
    gauge = GAUGES[slug]
    if not settings.twenty_configured:
        return JSONResponse(status_code=502, content={"error": "Twenty is not configured"})
    target = gauge["target"]
    target_param = request.query_params.get("target")
    if target_param:
        try:
            target = float(target_param)
        except ValueError:
            pass
    try:
        current = await _get_current_total(slug, gauge["match"])
    except (TwentyFetchError, httpx.HTTPError) as exc:
        return JSONResponse(status_code=502, content={"error": str(exc)})
    return {
        "current": current,
        "target": target,
        "currency": CURRENCY_CODE,
        "currencySymbol": CURRENCY_SYMBOL,
        "updatedAt": _cache[slug]["fetched_at_iso"],
        "title": gauge["title"],
        "desc": gauge["desc"],
    }


@router.get("/pipeline", dependencies=[Depends(_require_superadmin)])
async def pipeline(request: Request):
    """Kept at this exact path for backward compatibility — it's already the
    URL embedded in a live Twenty dashboard widget. Equivalent to GAUGES["won"]."""
    return await _gauge_data("won", request)


@router.get("/{slug}/data", dependencies=[Depends(_require_superadmin)])
async def gauge_slug_data(slug: str, request: Request):
    if slug not in GAUGES:
        raise HTTPException(status_code=404, detail=f"Unknown gauge {slug!r}")
    return await _gauge_data(slug, request)


# %%DATA_URL%% is replaced per-route below: "pipeline" for the legacy root
# page, "data" for a /{slug}/ page (relative to its own directory-style URL).
# Title/description are NOT baked in here — they come from the fetched JSON
# (gauge["title"]/["desc"]), so this one template serves every gauge.
_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Dashboard Gauge</title>
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
  .header { text-align: center; margin-bottom: clamp(2px, 1.5vw, 8px); min-height: 1.2em; }
  .title { font-size: clamp(0.8rem, 3.2vw, 1rem); font-weight: 650; letter-spacing: -0.01em; }
  .desc { margin-top: 2px; font-size: clamp(0.6rem, 2.2vw, 0.75rem); color: var(--muted); }
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
    <div class="header">
      <div class="title" id="title"></div>
      <div class="desc" id="desc"></div>
    </div>
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
  const titleEl = document.getElementById("title");
  const descEl = document.getElementById("desc");

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
    if (data.title) titleEl.textContent = data.title;
    if (data.desc) descEl.textContent = data.desc;

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
      let url = "%%DATA_URL%%";
      const override = targetOverride();
      if (override) url += "?target=" + encodeURIComponent(override);
      const resp = await fetch(url, { cache: "no-store" });
      if (!resp.ok) throw new Error("HTTP " + resp.status);
      render(await resp.json());
    } catch (err) {
      subEl.textContent = "Couldn't load data";
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

_CSP_HEADERS = {"Content-Security-Policy": f"frame-ancestors 'self' {ALLOWED_FRAME_ANCESTORS}"}


@router.get("/", dependencies=[Depends(_require_superadmin)], response_class=HTMLResponse)
async def gauge_page():
    """Kept at this exact path for backward compatibility — see `pipeline` above."""
    return HTMLResponse(content=_PAGE_HTML.replace("%%DATA_URL%%", "pipeline"), headers=_CSP_HEADERS)


@router.get("/{slug}/", dependencies=[Depends(_require_superadmin)], response_class=HTMLResponse)
async def gauge_slug_page(slug: str):
    if slug not in GAUGES:
        raise HTTPException(status_code=404, detail=f"Unknown gauge {slug!r}")
    return HTMLResponse(content=_PAGE_HTML.replace("%%DATA_URL%%", "data"), headers=_CSP_HEADERS)
