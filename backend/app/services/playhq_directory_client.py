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


async def _post(url: str, payload: dict, extra_headers: dict | None = None) -> Optional[dict]:
    """One GraphQL POST behind the concurrency gate, with a jittered courtesy
    delay and a single backoff-and-retry on 429/5xx. Returns the parsed ``data``
    object, or None on transport error / GraphQL errors."""
    headers = dict(_HEADERS)
    if extra_headers:
        headers.update(extra_headers)
    async with _SEMAPHORE:
        # Delay BEFORE the request so concurrent callers can't burst.
        await asyncio.sleep(random.uniform(
            settings.marketing_crawl_min_delay, settings.marketing_crawl_max_delay))
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
                               limit: int = 100) -> tuple[list[dict], int]:
    """One page of the org search. Returns (results, total_records). ``org_type``
    is an ``OrganisationType`` enum value (e.g. ``CLUB`` / ``ASSOCIATION``)."""
    payload = {
        "query": _SEARCH_QUERY,
        "variables": {"filter": {
            "meta": {"limit": limit, "page": page},
            "organisation": {"query": query, "types": [org_type], "sports": ["CRICKET"]},
        }},
    }
    data = await _post(settings.playhq_search_url, payload)
    if not data or not data.get("search"):
        return [], 0
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


async def discover_org_contact(routing_code: str) -> Optional[dict]:
    """The club's own org-level email/phone (the generic club mailbox PlayHQ shows
    on the org page) via the main graph. Returns ``{"email", "phone"}`` (either may
    be ""), or None on fetch failure. Separate from the committee ``contacts[]``,
    which the search endpoint already gives us."""
    if not routing_code:
        return None
    data = await _post(
        settings.playhq_graph_url,
        {"query": _ORG_QUERY, "variables": {"c": routing_code}},
        extra_headers={"tenant": settings.playhq_tenant})
    if data is None:
        return None
    org = data.get("discoverOrganisation")
    if not org:
        return None
    return {"email": (org.get("email") or "").strip(),
            "phone": (org.get("contactNumber") or "").strip()}
