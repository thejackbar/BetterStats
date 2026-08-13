"""BetterScout — the REAL search engine behind play.cricket.com.au's own
header search box.

Found by inspecting a live club page's DOM (`data-widget="global-search/
global-search-header"`, `data-global-search-path="/search-new"`), pulling
the actual widget chunk it lazy-loads (`global-search-header.js` /
`global-search-page.js` off the same CDN as the page's own bundle), and
watching the network request the results page fires:

    GET https://api.playcommunity.pulselive.com/ca-search/v1/playCommunity
        ?types=PLAYCOMM_CLUB&types=PLAYCOMM_PLAYER&term=<name>
        &size=20&page=0&sorting=ASC&tags=search

Confirmed live, unauthenticated, no CORS enforcement server-side (CORS is a
browser-only mechanism — a plain server-to-server request works identically
to what the browser sends). Same undocumented-but-load-bearing posture this
codebase already takes with `grassrootsapiproxy.cricket.com.au` — never
officially published, so every call here is defensive: short timeout, any
failure degrades to an empty result rather than raising, and nothing here
is assumed stable across a PlayHQ deploy.

This is a genuinely different, better primitive than the club-cache-scan
BetterScout used before this file existed:
  - CLUB search is now real and national, not limited to clubs someone has
    already looked up on Discover.
  - PLAYER search returns one canonical identity per real person, carrying
    their REAL `organisations` list directly — e.g. Spencer Green's `id`
    (which matches his own play.cricket.com.au profile URL exactly) lists
    all 12 real clubs/rep sides he's registered at. This is authoritative
    membership data, not a name-similarity guess — see
    services/scout_discovery.suggest_other_clubs, which reads it directly
    instead of fuzzy-scanning whatever's cached.
"""
from __future__ import annotations

import logging

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://api.playcommunity.pulselive.com/ca-search/v1"
DEFAULT_TIMEOUT = 12.0
DEFAULT_SIZE = 20


async def search_playcommunity(
    term: str, *, types: tuple[str, ...] = ("PLAYCOMM_CLUB", "PLAYCOMM_PLAYER"), size: int = DEFAULT_SIZE,
) -> dict:
    """Returns `{"clubs": [...], "players": [...]}`. Never raises — a
    network hiccup or an upstream shape change degrades to an empty result,
    same as every other external-API wrapper in this codebase."""
    term = (term or "").strip()
    if not term:
        return {"clubs": [], "players": []}
    params = [("term", term), ("size", size), ("page", 0), ("sorting", "ASC"), ("tags", "search")]
    params += [("types", t) for t in types]
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{BASE_URL}/playCommunity", params=params, timeout=DEFAULT_TIMEOUT,
                headers={"Accept": "application/json"},
            )
            if r.status_code >= 400:
                logger.warning(f"scout_live_search: {r.status_code} for {term!r}: {r.text[:150]}")
                return {"clubs": [], "players": []}
            data = r.json()
    except Exception as e:
        logger.warning(f"scout_live_search: request failed for {term!r}: {e}")
        return {"clubs": [], "players": []}

    # organisationGuid, not playHQId — same rule playhq_client.search_organisations
    # already documents: the Grassroots/sync org id is what every roster-build
    # call actually resolves against; playHQId is a different namespace.
    clubs = [
        {"id": c.get("organisationGuid"), "name": c.get("name"), "state": c.get("stateName")}
        for c in ((data.get("clubs") or {}).get("items") or [])
        if c.get("organisationGuid") and c.get("name")
    ]
    players = [
        {
            "id": p.get("id"),
            "name": p.get("name"),
            "organisations": [
                {"id": o.get("id"), "name": o.get("name")}
                for o in (p.get("organisations") or []) if o.get("id") and o.get("name")
            ],
        }
        for p in ((data.get("players") or {}).get("items") or [])
        if p.get("id") and p.get("name")
    ]
    return {"clubs": clubs, "players": players}
