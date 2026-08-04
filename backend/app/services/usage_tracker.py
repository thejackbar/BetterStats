"""Usage breadcrumbs — fire-and-forget event recorder.

Drops a row into `usage_events` for every interesting API call and SPA
page view so we can see what features people actually use. Deliberately
silent on failure — tracking must never break a real request.

Geo enrichment:
  - Country comes from Cloudflare's `cf-ipcountry` header (free on every
    CF plan) — captured by the caller and passed in at insert time.
  - City + region + a city-centroid lat/lng come from a follow-up
    ip-api.com lookup (free, no key, 45 req/min/IP) cached in-process by
    IP hash. The lookup runs after the row is written and UPDATEs the row
    in place. We never store the raw IP — only the location resolved from
    it, and only ever at city precision (never street-level).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import uuid as _uuid
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

# ip_hashes with an ip-api.com lookup in flight right now. A visitor's first
# few events land within milliseconds of each other — all before the lookup
# that fills _GEO_CACHE has returned — so without this every one of them fires
# its own lookup AND its own backfill UPDATE against the same set of rows.
_GEO_INFLIGHT: set[str] = set()

# How far back the post-lookup backfill reaches. Its job is only to catch the
# rows that landed while the lookup was in flight (a second or two), so an hour
# is already generous. It used to be unbounded, which meant re-visiting every
# row this IP had ever written — most of them rows that had already failed
# enrichment and would fail again — on every fresh lookup.
_GEO_BACKFILL_WINDOW = "1 hour"

# Ceiling on how many background tracking writes may hold a DB connection at
# once. Breadcrumbs are fire-and-forget and unbounded in number (one per
# request via the middleware, plus a heartbeat per open tab every ~25s), and
# each one opens its own session. With no ceiling, a burst of traffic drains
# the SQLAlchemy pool out from under real requests — which is how
# /club-admin/usage/geo came to fail on "QueuePool limit of size 20 overflow
# 30 reached" before its handler ever ran (the timeout hit in get_current_user).
# Tracking is the lowest-value user of a connection, so it gets a small slice.
_DB_SLOTS = asyncio.Semaphore(6)

# Beyond this many breadcrumbs waiting on a slot we drop rather than queue: a
# lost breadcrumb is invisible, a backlog that outlives the burst is not.
_MAX_PENDING = 500
_pending = 0

# asyncio only holds a weak reference to a task, so a fire-and-forget one can
# be garbage-collected mid-flight. Keep a strong ref until it finishes.
_BG_TASKS: set = set()


async def _guard(coro) -> None:
    """Swallow anything that escapes a background tracking coroutine. Without
    this an escaped error surfaces as asyncio's "Task exception was never
    retrieved" dump — noise from a subsystem whose whole contract is that it
    never disturbs the request it fired alongside."""
    try:
        await coro
    except asyncio.CancelledError:
        raise
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: background task failed ({e})")


def _spawn(coro) -> bool:
    """Fire a background coroutine, keeping a strong reference. False if
    there's no running loop (a sync context — nothing to schedule on)."""
    try:
        task = asyncio.get_running_loop().create_task(_guard(coro))
    except RuntimeError:
        coro.close()
        return False
    _BG_TASKS.add(task)
    task.add_done_callback(_BG_TASKS.discard)
    return True


def hash_ip(ip: Optional[str]) -> Optional[str]:
    if not ip:
        return None
    return hashlib.sha256(ip.encode("utf-8")).hexdigest()[:16]


# ─── Traffic-source bucketing ────────────────────────────────────────────────
# We bucket each visitor's *first-touch* acquisition into a single readable
# label at insert time so the Usage page can group on it cheaply. Strongest
# signal wins: an explicit utm_source, then the ad-network click id the client
# detected (fbclid → facebook, gclid → google …), then the referring host,
# then "direct".

# Normalise the messy spellings people put in utm_source.
_UTM_SOURCE_NORM = {
    "fb": "facebook", "facebook": "facebook", "meta": "facebook",
    "facebook.com": "facebook", "messenger": "facebook",
    "ig": "instagram", "instagram": "instagram",
    "google": "google", "adwords": "google", "googleads": "google",
    "google-ads": "google", "gmb": "google",
    "bing": "bing", "microsoft": "bing",
    "tiktok": "tiktok", "tik-tok": "tiktok",
    "linkedin": "linkedin", "twitter": "twitter", "x": "twitter",
    "youtube": "youtube", "yt": "youtube",
    "reddit": "reddit", "whatsapp": "whatsapp",
    "email": "email", "newsletter": "email", "mailchimp": "email",
    "mailerlite": "email", "sendgrid": "email", "klaviyo": "email",
}

# Referrer-host substrings → bucket. Checked in order.
_HOST_SOURCE = (
    ("l.facebook.", "facebook"), ("lm.facebook.", "facebook"),
    ("m.facebook.", "facebook"), ("facebook.", "facebook"), ("fb.", "facebook"),
    ("instagram.", "instagram"), ("l.instagram.", "instagram"),
    ("google.", "google"), ("googleads.", "google"), ("googlesyndication.", "google"),
    ("bing.", "bing"), ("duckduckgo.", "duckduckgo"), ("yahoo.", "yahoo"),
    ("t.co", "twitter"), ("twitter.", "twitter"), ("x.com", "twitter"),
    ("linkedin.", "linkedin"), ("lnkd.in", "linkedin"),
    ("youtube.", "youtube"), ("youtu.be", "youtube"),
    ("tiktok.", "tiktok"), ("reddit.", "reddit"),
    ("whatsapp.", "whatsapp"), ("wa.me", "whatsapp"),
    ("play.cricket.com.au", "playcricket"), ("playhq.com", "playhq"),
)

# Our own hosts — a referrer here is internal navigation, not an acquisition.
_INTERNAL_HOST_BITS = ("betterat.cricket", "betterstats.cricket",
                       "betterstats.bltbox", "localhost", "127.0.0.1")


def _host_of(url: Optional[str]) -> Optional[str]:
    if not url:
        return None
    s = url.strip().lower()
    if "//" in s:
        s = s.split("//", 1)[1]
    s = s.split("/", 1)[0].split("?", 1)[0]
    return s or None


def derive_traffic_source(
    utm_source: Optional[str],
    utm_medium: Optional[str],
    click_id: Optional[str],
    click_source: Optional[str],
    referrer: Optional[str],
) -> Optional[str]:
    """Bucket a first-touch acquisition into one readable source label."""
    src = (utm_source or "").strip().lower()
    if src:
        return _UTM_SOURCE_NORM.get(src, src)[:40]
    # Ad-network click id the client classified for us (fbclid → facebook …).
    cs = (click_source or "").strip().lower()
    if cs:
        return cs[:40]
    cid = (click_id or "").strip().lower()
    if cid.startswith("fbclid") or "fbclid=" in cid:
        return "facebook"
    if cid.startswith("gclid") or cid.startswith("gbraid") or cid.startswith("wbraid"):
        return "google"
    # Referrer host.
    host = _host_of(referrer)
    if host:
        if any(bit in host for bit in _INTERNAL_HOST_BITS):
            return None  # internal navigation — leave first-touch unset
        for needle, bucket in _HOST_SOURCE:
            if needle in host:
                return bucket
        return host[:40]  # bare external host as the referral source
    return "direct"


def _valid_uuid(value: Optional[str]) -> Optional[str]:
    """Return a lowercase UUID string, or None if not a valid UUID. Keeps a
    bad client-supplied visitor_id from poisoning a UUID column."""
    if not value:
        return None
    try:
        return str(_uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        return None


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
    visitor_id: Optional[str] = None,
    utm_source: Optional[str] = None,
    utm_medium: Optional[str] = None,
    utm_campaign: Optional[str] = None,
    utm_content: Optional[str] = None,
    utm_id: Optional[str] = None,
    click_id: Optional[str] = None,
    click_source: Optional[str] = None,
    landing_referrer: Optional[str] = None,
    landing_path: Optional[str] = None,
    time_on_page_ms: Optional[int] = None,
) -> None:
    """Insert one breadcrumb. Opens its own session so it can run after the
    request session has been closed. Never raises."""
    ip_h = hash_ip(ip)
    region = None
    city = None
    lat = None
    lng = None
    # Cached city/region/coords for this IP, if we've already looked it up.
    cached = _GEO_CACHE.get(ip_h) if ip_h else None
    if cached:
        country = country or cached.get("country")
        region = cached.get("region")
        city = cached.get("city")
        lat = cached.get("lat")
        lng = cached.get("lng")

    visitor = _valid_uuid(visitor_id)
    # First-touch acquisition source, bucketed once at insert time. Only the
    # page-view beacon supplies these; API rows leave them NULL.
    traffic_source = derive_traffic_source(
        utm_source, utm_medium, click_id, click_source,
        landing_referrer or referer,
    ) if event_type == "page_view" else None

    try:
        async with _DB_SLOTS, async_session_maker() as session:
            result = await session.execute(
                text(
                    """
                    INSERT INTO usage_events (
                        event_type, method, path, route, status, duration_ms,
                        user_id, org_id, ip_hash, user_agent, referer,
                        country, region, city, lat, lng, metadata,
                        visitor_id, utm_source, utm_medium, utm_campaign,
                        utm_content, utm_id, click_id, traffic_source, landing_path,
                        time_on_page_ms
                    ) VALUES (
                        :event_type, :method, :path, :route, :status, :duration_ms,
                        :user_id, :org_id, :ip_hash, :user_agent, :referer,
                        :country, :region, :city, :lat, :lng,
                        CAST(:metadata AS JSONB),
                        :visitor_id, :utm_source, :utm_medium, :utm_campaign,
                        :utm_content, :utm_id, :click_id, :traffic_source, :landing_path,
                        :time_on_page_ms
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
                    "lat": lat,
                    "lng": lng,
                    "metadata": json.dumps(metadata or {}),
                    "visitor_id": visitor,
                    "utm_source": (utm_source or "")[:120] or None,
                    "utm_medium": (utm_medium or "")[:120] or None,
                    "utm_campaign": (utm_campaign or "")[:200] or None,
                    "utm_content": (utm_content or "")[:200] or None,
                    "utm_id": (utm_id or "")[:200] or None,
                    "click_id": (click_id or "")[:300] or None,
                    "traffic_source": traffic_source,
                    "landing_path": (landing_path or "")[:500] or None,
                    # Sanity-clamp: a beacon can't reliably report more than a day
                    # on one page — a bad clock or a stuck timer shouldn't skew averages.
                    "time_on_page_ms": (
                        max(0, min(int(time_on_page_ms), 24 * 60 * 60 * 1000))
                        if time_on_page_ms is not None else None
                    ),
                },
            )
            row_id = result.scalar()
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: record_event failed ({e})")
        return

    # Schedule a follow-up city/region lookup if we have an IP, haven't
    # cached it yet, no lookup for this IP is already running, and the country
    # isn't a private marker. Updates the row we just wrote.
    #
    # Re-read the cache here rather than reusing `cached` from the top of the
    # function: that value was captured before the insert waited on a DB slot,
    # so by now another event's lookup for this same IP may well have landed.
    # Trusting the stale read means every burst fires a fresh round of
    # redundant lookups the moment the in-flight one clears.
    if (ip and ip_h and row_id
            and ip_h not in _GEO_CACHE
            and ip_h not in _GEO_INFLIGHT
            and (country or "").upper() not in _GEO_SKIP_COUNTRIES):
        _GEO_INFLIGHT.add(ip_h)
        if not _spawn(_enrich_geo(ip=ip, ip_hash=ip_h, row_id=row_id, country=country)):
            _GEO_INFLIGHT.discard(ip_h)

    # CRM — event-driven check (no periodic sweep anywhere) for the
    # score-based Target/Contacted -> Engaged rule (crm.py). Skip an
    # authenticated admin-panel request outright (the biggest single source
    # of volume, and never a signal for a still-prospect club anyway — an
    # onboarded club's own org_id is caught by user_id-less public traffic to
    # its site instead); crm.check_web_signal_promotion's own two gates
    # (resolve a club at all, then does it even have an open early-stage
    # deal) filter out virtually everything else before doing any real work.
    # A heartbeat is skipped too: it's a "still here" ping for a page whose own
    # page_view already fired this check moments earlier, carrying no
    # attribution of its own. Running it per heartbeat means a session and a
    # club resolution every ~25s per open tab for a signal already counted.
    if event_type != "heartbeat" and not (
            user_id and path and path.split("?", 1)[0].lower().startswith("/admin")):
        from app.services.crm import check_web_signal_promotion
        _spawn(check_web_signal_promotion(
            org_id=org_id, utm_id=utm_id, utm_source=utm_source,
            path=path, user_id=user_id, event_id=row_id))


async def _enrich_geo(*, ip: str, ip_hash: str, row_id: int, country: Optional[str]) -> None:
    """Look up city/region/coords via ip-api.com, cache, and UPDATE the row.

    ip-api.com free tier: 45 req/min/IP, no key, JSON. Their TOS allows
    non-commercial use. Endpoint: http://ip-api.com/json/{ip}. lat/lon are
    the geolocation database's own city-centroid coordinates — the same
    precision ceiling as regionName/city, never street-level.

    Always clears its own _GEO_INFLIGHT entry, including on the early returns —
    leaving one set would permanently block re-lookup of that IP.
    """
    try:
        await _enrich_geo_inner(ip=ip, ip_hash=ip_hash, row_id=row_id, country=country)
    finally:
        _GEO_INFLIGHT.discard(ip_hash)


async def _enrich_geo_inner(*, ip: str, ip_hash: str, row_id: int, country: Optional[str]) -> None:
    empty = {"country": country, "region": None, "city": None, "lat": None, "lng": None}
    try:
        async with httpx.AsyncClient(timeout=_GEO_LOOKUP_TIMEOUT) as client:
            resp = await client.get(
                f"http://ip-api.com/json/{ip}",
                params={"fields": "status,country,countryCode,regionName,city,lat,lon"},
            )
            if resp.status_code != 200:
                _GEO_CACHE[ip_hash] = empty
                return
            data = resp.json()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: geo lookup failed for {ip_hash}: {e}")
        _GEO_CACHE[ip_hash] = empty
        return

    if data.get("status") != "success":
        _GEO_CACHE[ip_hash] = empty
        return

    cc = (data.get("countryCode") or country or "").upper()[:2] or None
    region = data.get("regionName") or None
    city = data.get("city") or None
    lat = data.get("lat")
    lng = data.get("lon")
    try:
        lat = float(lat) if lat is not None else None
        lng = float(lng) if lng is not None else None
    except (TypeError, ValueError):
        lat = None
        lng = None

    # Soft-bound the cache.
    if len(_GEO_CACHE) >= _GEO_CACHE_CAP:
        # Drop ~10% of the oldest entries by simple FIFO order.
        for k in list(_GEO_CACHE.keys())[: _GEO_CACHE_CAP // 10]:
            _GEO_CACHE.pop(k, None)
    _GEO_CACHE[ip_hash] = {"country": cc, "region": region, "city": city, "lat": lat, "lng": lng}

    try:
        async with _DB_SLOTS, async_session_maker() as session:
            # Backfill this row plus any other rows with the same IP hash
            # that landed before the lookup finished — they all share
            # location.
            #
            # Both bounds matter. The created_at window keeps this to the
            # handful of rows the lookup raced, and rides the (ip_hash,
            # created_at) index; unbounded, it re-examined every row this IP
            # had ever written. usage_events is append-only with no retention
            # job, so on an unindexed column that was a full table scan per
            # newly-seen IP, holding a connection and row locks for the
            # duration — the pileup that drained the connection pool. The
            # id = :row_id arm guarantees the triggering row is always covered
            # even if the clock or the window ever disagrees.
            await session.execute(
                text(
                    f"""
                    UPDATE usage_events
                    SET country = COALESCE(:country, country),
                        region  = COALESCE(:region,  region),
                        city    = COALESCE(:city,    city),
                        lat     = COALESCE(:lat,     lat),
                        lng     = COALESCE(:lng,     lng)
                    WHERE (region IS NULL OR city IS NULL)
                      AND (
                        id = :row_id
                        OR (ip_hash = :ip_hash
                            AND created_at >= NOW() - INTERVAL '{_GEO_BACKFILL_WINDOW}')
                      )
                    """
                ),
                {"country": cc, "region": region, "city": city, "lat": lat,
                 "lng": lng, "ip_hash": ip_hash, "row_id": row_id},
            )
            await session.commit()
    except Exception as e:  # noqa: BLE001
        logger.debug(f"usage_tracker: geo backfill update failed: {e}")


async def _record_event_counted(**kwargs) -> None:
    global _pending
    try:
        await record_event(**kwargs)
    finally:
        _pending -= 1


def record_event_bg(**kwargs) -> None:
    """Schedule record_event without awaiting it. Drops the breadcrumb rather
    than queueing it once _MAX_PENDING are already waiting on a DB slot."""
    global _pending
    if _pending >= _MAX_PENDING:
        logger.debug("usage_tracker: breadcrumb dropped, %s already pending", _pending)
        return
    _pending += 1
    if not _spawn(_record_event_counted(**kwargs)):
        _pending -= 1
