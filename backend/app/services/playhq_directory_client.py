"""PlayHQ public discovery client — enumerate Australian cricket clubs and map
each to the association(s) it plays in.

Two public PlayHQ GraphQL endpoints back this, both reachable unauthenticated
(no API key) the same way the playhq.com website reads them:

1. **Search** (``settings.playhq_search_url`` = ``https://search.playhq.com/graphql``)
   ``search(filter: SearchFilter)`` over organisations. An empty ``query`` with
   ``sports:[CRICKET]`` and ``types:[CLUB]`` enumerates the whole list, paged.
   Each ``Organisation`` carries ``id`` (GUID), ``routingCode`` (the short code
   the main graph keys on), ``name``, ``websiteUrl``, ``address`` and the full
   committee ``contacts[]`` (name + position + email + phone). ``tenant`` is the
   governing body, so Australia is ``tenant.name == "Cricket Australia"``.

2. **Main graph** (``settings.playhq_graph_url`` = ``https://api.playhq.com/graphql``)
   ``discoverCompetitions(organisationID: routingCode)`` — each competition's
   ``organisation`` (type ``ASSOCIATION``) is an association the club plays in.
   This endpoint routes per tenant, so it needs a ``tenant`` header
   (``cricket-australia``); without it the server returns "Bolt adapter map not
   found". It keys on the **routingCode**, not the search GUID.

Politeness mirrors the rest of the marketing crawl (``marketing_crawl_*``):
one request at a time, a jittered courtesy delay, a single 429/5xx backoff. We
read the same public endpoints the website does and identify as a normal client.
"""
from __future__ import annotations

import asyncio
import logging
import random
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

_TIMEOUT = 30.0
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept": "application/json",
    "Content-Type": "application/json",
    "Origin": "https://www.playhq.com",
    "Referer": "https://www.playhq.com/",
}

# A slow, polite background walk — one request at a time (the live sync uses 6).
_SEMAPHORE = asyncio.Semaphore(1)

# GraphQL documents (lifted from the playhq.com bundle, trimmed to what we store).
_SEARCH_QUERY = (
    "query Directory($filter: SearchFilter!){ "
    "search(filter:$filter){ "
    "results{ ... on Organisation { "
    "id routingCode name type websiteUrl "
    "tenant{ name } "
    "address{ line1 suburb postcode state country latitude longitude } "
    "contacts{ firstName lastName position email phone visible } } } "
    "meta{ page totalRecords } } }"
)
_COMPETITIONS_QUERY = (
    "query Comps($id: ID!){ discoverCompetitions(organisationID:$id){ "
    "id name organisation{ id name type } } }"
)
# Some clubs publish a single org-level email/phone (a generic club mailbox) but
# no individual committee contacts — the search ``contacts[]`` is then empty, but
# the main graph's ``discoverOrganisation`` still carries ``email``/``contactNumber``.
_ORG_QUERY = (
    "query Org($c: String!){ discoverOrganisation(code:$c){ "
    "id email contactNumber } }"
)


async def _post(url: str, payload: dict, extra_headers: dict | None = None,
                min_delay: float | None = None, max_delay: float | None = None) -> Optional[dict]:
    """One GraphQL POST behind the concurrency gate, with a jittered courtesy
    delay and a single backoff-and-retry on 429/5xx. Returns the parsed ``data``
    object, or None on transport error / GraphQL errors. ``min_delay``/``max_delay``
    override the (polite, slow) crawl delay — used for short interactive lookups."""
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    lo = settings.marketing_crawl_min_delay if min_delay is None else min_delay
    hi = settings.marketing_crawl_max_delay if max_delay is None else max_delay
    async with _SEMAPHORE:
        # Delay BEFORE the request so concurrent callers can't burst.
        await asyncio.sleep(random.uniform(lo, hi))
        async with httpx.AsyncClient(timeout=_TIMEOUT, headers=headers) as client:
            for attempt in (1, 2):
                try:
                    r = await client.post(url, json=payload)
                except httpx.HTTPError as exc:
                    logger.warning("playhq_directory POST %s failed: %s", url, exc)
                    if attempt == 1:
                        await asyncio.sleep(8.0)
                        continue
                    return None
                if r.status_code in (429, 500, 502, 503) and attempt == 1:
                    await asyncio.sleep(8.0)
                    continue
                try:
                    body = r.json()
                except ValueError:
                    return None
                if body.get("errors"):
                    logger.info("playhq_directory GraphQL errors on %s: %s",
                                url, body["errors"][:1])
                return body.get("data")
    return None


async def search_organisations(org_type: str, query: str = "", page: int = 1,
                               limit: int = 100) -> tuple[Optional[list[dict]], int]:
    """One page of the org search. Returns (results, total_records). ``org_type``
    is an ``OrganisationType`` enum value (e.g. ``CLUB`` / ``ASSOCIATION``).
    ``results`` is **None on a fetch failure** (so the caller can retry rather than
    mistake a transient error for the end of the list), and an empty list only when
    the page genuinely has no results."""
    payload = {
        "query": _SEARCH_QUERY,
        "variables": {"filter": {
            "meta": {"limit": limit, "page": page},
            "organisation": {"query": query, "types": [org_type], "sports": ["CRICKET"]},
        }},
    }
    data = await _post(settings.playhq_search_url, payload)
    if data is None or data.get("search") is None:
        return None, 0
    search = data["search"]
    results = [r for r in (search.get("results") or []) if r]
    total = (search.get("meta") or {}).get("totalRecords") or 0
    return results, total


async def discover_associations(routing_code: str) -> Optional[list[dict]]:
    """The association(s) a club plays in, via the main graph's competitions.
    Returns a deduped list of ``{"id", "name", "competition"}`` (one per running
    association), an empty list when the club has none, or None on fetch failure
    (so the caller can leave it as a retryable frontier)."""
    if not routing_code:
        return []
    data = await _post(
        settings.playhq_graph_url,
        {"query": _COMPETITIONS_QUERY, "variables": {"id": routing_code}},
        extra_headers={"tenant": settings.playhq_tenant})
    if data is None:
        return None
    comps = data.get("discoverCompetitions")
    if comps is None:
        return None
    seen: dict[str, dict] = {}
    for comp in comps:
        org = (comp or {}).get("organisation") or {}
        if (org.get("type") == "ASSOCIATION") and org.get("id") and org["id"] not in seen:
            seen[org["id"]] = {
                "id": org["id"], "name": org.get("name") or "",
                "competition": (comp or {}).get("name") or "",
            }
    return list(seen.values())


async def discover_org_contact(routing_code: str, delay: tuple | None = None) -> Optional[dict]:
    """The club's own org-level email/phone (the generic club mailbox PlayHQ shows
    on the org page) via the main graph. Returns ``{"email", "phone"}`` (either may
    be ""), or None on fetch failure. Separate from the committee ``contacts[]``,
    which the search endpoint already gives us."""
    if not routing_code:
        return None
    lo, hi = (delay or (settings.marketing_crawl_min_delay, settings.marketing_crawl_max_delay))
    data = await _post(
        settings.playhq_graph_url,
        {"query": _ORG_QUERY, "variables": {"c": routing_code}},
        extra_headers={"tenant": settings.playhq_tenant}, min_delay=lo, max_delay=hi)
    if data is None:
        return None
    org = data.get("discoverOrganisation")
    if not org:
        return None
    return {"email": (org.get("email") or "").strip(),
            "phone": (org.get("contactNumber") or "").strip()}


# ── authoritative association → clubs roster ────────────────────────────────────
# The directory's per-club association list is only as complete as the enrichment
# pass. To get an association's FULL roster on demand we walk it from the top:
#   association → discoverCompetitions → seasons → discoverSeason.grades →
#   discoverGrade.ladder.standings.team.organisation
# Each standing's team.organisation is a member club (id == its routingCode).
# These run on a SHORT delay (interactive operator action, low volume), not the
# slow background-crawl delay.
_GRAPH_TENANT = lambda: {"tenant": settings.playhq_tenant}  # noqa: E731
_INTERACTIVE_DELAY = (0.2, 0.7)

_ASSOC_COMPS_QUERY = (
    "query AC($id: ID!){ discoverCompetitions(organisationID:$id){ "
    "id name seasons(organisationID:$id){ id name status{ value } } } }"
)
_SEASON_GRADES_QUERY = (
    "query SG($id: String!){ discoverSeason(seasonID:$id){ id name grades{ id name } } }"
)
_GRADE_CLUBS_QUERY = (
    "query GC($id: ID!){ discoverGrade(gradeID:$id){ "
    "ladder{ standings{ team{ organisation{ id name } } } } } }"
)


async def _post_graph(payload: dict, delay: tuple | None = None) -> Optional[dict]:
    lo, hi = delay or _INTERACTIVE_DELAY
    return await _post(settings.playhq_graph_url, payload, extra_headers=_GRAPH_TENANT(),
                       min_delay=lo, max_delay=hi)


async def association_seasons(assoc_routing_code: str, delay: tuple | None = None) -> list[dict]:
    """The association's competitions' seasons, newest-first as returned:
    ``[{"id","name","status"}]``."""
    data = await _post_graph({"query": _ASSOC_COMPS_QUERY, "variables": {"id": assoc_routing_code}}, delay)
    comps = (data or {}).get("discoverCompetitions") or []
    out = []
    for comp in comps:
        for s in (comp.get("seasons") or []):
            out.append({"id": s.get("id"), "name": s.get("name") or "",
                        "status": ((s.get("status") or {}).get("value") or "")})
    return out


async def season_grade_ids(season_id: str, delay: tuple | None = None) -> list[str]:
    data = await _post_graph({"query": _SEASON_GRADES_QUERY, "variables": {"id": season_id}}, delay)
    season = (data or {}).get("discoverSeason") or {}
    return [g["id"] for g in (season.get("grades") or []) if g.get("id")]


async def grade_club_orgs(grade_id: str, delay: tuple | None = None) -> list[dict]:
    """Distinct member clubs of a grade (from the ladder standings):
    ``[{"id" (routingCode), "name"}]``."""
    data = await _post_graph({"query": _GRADE_CLUBS_QUERY, "variables": {"id": grade_id}}, delay)
    grade = (data or {}).get("discoverGrade") or {}
    seen: dict[str, str] = {}
    for pool in (grade.get("ladder") or []):
        for st in ((pool or {}).get("standings") or []):
            org = ((st or {}).get("team") or {}).get("organisation") or {}
            if org.get("id") and org["id"] not in seen:
                seen[org["id"]] = org.get("name") or ""
    return [{"id": k, "name": v} for k, v in seen.items()]
