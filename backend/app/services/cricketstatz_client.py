"""CricketStatz public-report client.

Fetches a club's OWN reports from its public CricketStatz site so the club can
bring its history into BetterCricket. This is a data-portability path a club
runs against its own records, on demand — one club at a time, never a crawl of
the wider site — so the client is deliberately conservative:

* a low concurrency ceiling and a small delay between requests,
* an in-process cache so a preview followed by an import does not refetch,
* a User-Agent that says who we are and why.

Everything is served by the documented embed endpoint::

    /ss/linkreport?mode=<report>&club=<id>&web=1

`limit` caps a report at 999 rows, so match lists are pulled SEASON BY SEASON
rather than all-time: an all-time pull silently truncates at 999 for a club
with a long history, and a truncated history is worse than a slow one.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

import httpx

from app.services.cricketstatz_parse import (
    CricketStatzError,
    parse_club_page,
    parse_report,
    parse_results,
    parse_scorecard,
)

logger = logging.getLogger(__name__)

BASE = "https://www2.cricketstatz.com/ss"
TIMEOUT = 30.0
# One club's history at a time, gently. Their reports are generated per
# request, so this is a real cost on someone else's server.
_SEMAPHORE = asyncio.Semaphore(3)
_DELAY = 0.25
_MAX_ROWS = 999  # the endpoint's own ceiling

_HEADERS = {
    "User-Agent": (
        "BetterCricket/1.0 (club data export on behalf of the club that owns "
        "it; support@bettersports.com.au)"
    ),
    "Accept": "text/html,application/xhtml+xml",
}

# mode -> the report that carries it
MODE_RESULTS = 12
MODE_MATCH = 100
MODE_TEAMS = 107

_cache: dict[str, tuple[float, str]] = {}
_CACHE_TTL = 1800  # a preview and the import that follows share one pull


class CricketStatzUnavailable(RuntimeError):
    """The site could not be reached at all."""


async def _get(path: str, params: dict, *, cache: bool = True) -> str:
    key = f"{path}?{sorted(params.items())}"
    now = time.time()
    if cache:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_TTL:
            return hit[1]

    async with _SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, headers=_HEADERS,
                                         follow_redirects=True) as client:
                resp = await client.get(f"{BASE}/{path}", params=params)
        except httpx.HTTPError as exc:
            raise CricketStatzUnavailable(
                f"Could not reach CricketStatz: {exc}"
            ) from exc
        await asyncio.sleep(_DELAY)

    if resp.status_code == 404:
        raise CricketStatzError("CricketStatz has no such report.", kind="not_found")
    if resp.status_code >= 400:
        raise CricketStatzUnavailable(
            f"CricketStatz returned HTTP {resp.status_code}."
        )
    body = resp.text
    if cache:
        _cache[key] = (now, body)
    return body


async def fetch_club_page(club_id: str) -> dict:
    """The club's own results page — its name, season list and team list."""
    async with _SEMAPHORE:
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT, headers=_HEADERS,
                                         follow_redirects=True) as client:
                resp = await client.get(
                    f"{BASE}/w",
                    params={"mode": MODE_RESULTS, "club": club_id,
                            "team": 0, "season": ""},
                )
        except httpx.HTTPError as exc:
            raise CricketStatzUnavailable(
                f"Could not reach CricketStatz: {exc}"
            ) from exc
        await asyncio.sleep(_DELAY)

    if resp.status_code >= 400:
        raise CricketStatzError(
            "CricketStatz did not recognise that club number.", kind="not_found"
        )
    page = parse_club_page(resp.text)
    if not page["seasons"]:
        raise CricketStatzError(
            "That page did not look like a CricketStatz club site.",
            kind="not_a_club",
        )
    return page


async def fetch_results(club_id: str, season: Optional[str] = None) -> list[dict]:
    """Match rows for one season (or every season when `season` is None)."""
    params = {"mode": MODE_RESULTS, "club": club_id, "web": 1, "limit": _MAX_ROWS}
    if season:
        params["season"] = season
    return parse_results(await _get("linkreport", params))


async def fetch_scorecard(club_id: str, match_id: str) -> dict:
    """The full two-team scorecard for one match."""
    # Deliberately uncached: a scorecard is fetched once per import and never
    # again, so keeping thousands of ~20KB bodies alive for the cache's TTL
    # holds a club's whole history in memory to no purpose.
    card = parse_scorecard(await _get(
        "linkreport",
        {"mode": MODE_MATCH, "match": match_id, "club": club_id, "web": 1},
        cache=False,
    ))
    card["source_match_id"] = str(match_id)
    return card


async def fetch_teams(club_id: str) -> list[dict]:
    from app.services.cricketstatz_parse import parse_teams
    return parse_teams(await _get(
        "linkreport", {"mode": MODE_TEAMS, "club": club_id, "web": 1}))


async def fetch_report(club_id: str, mode: int) -> dict:
    """One record/leaderboard report."""
    return parse_report(await _get(
        "linkreport",
        {"mode": mode, "club": club_id, "web": 1, "limit": 100},
    ))


async def probe_seasons(club_id: str, seasons: list[dict],
                        on_progress=None) -> list[dict]:
    """Which of the site's candidate seasons this club actually played.

    CricketStatz offers every season back to 1860 in its dropdown regardless of
    the club, so the list has to be probed rather than trusted. Each entry
    comes back with the number of matches found.
    """
    found: list[dict] = []
    for idx, season in enumerate(seasons):
        try:
            rows = await fetch_results(club_id, season["value"])
        except CricketStatzError:
            raise
        except Exception as exc:  # a single season must not sink the scan
            logger.warning("CricketStatz season %s failed: %s", season["value"], exc)
            rows = []
        if rows:
            found.append({**season, "match_count": len(rows)})
        if on_progress:
            on_progress(idx + 1, len(seasons), len(found))
    return found
