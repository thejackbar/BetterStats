"""Grassroots /scores/* client — Cricket Australia's pre-PlayHQ match data.

The grassrootsapiproxy hosts /scores/teams/{id}/matches and
/scores/matches/{id}?responseModifier=includeScorecard, both unauthenticated
beyond the standard jsconfig flag. These reach historical match data going
back to at least 1975 (pre-PlayHQ-migration). Post-migration games return 204 — that
signals "not mine" cleanly, no de-dup needed.

participantId values in the response correspond directly to our players.id
column (both are Grassroots GUIDs), so no extra mapping table is required.
"""
import asyncio
import logging
from typing import Optional

import httpx

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.playhq_base_url  # grassrootsapiproxy.cricket.com.au
TIMEOUT = 20.0
_SEMAPHORE = asyncio.Semaphore(6)
_JSCONFIG = "eccn:true"
_HEADERS = {
    "User-Agent": "BetterStats/1.0",
    "Accept": "application/json",
    "Origin": "https://play.cricket.com.au",
    "Referer": "https://play.cricket.com.au/",
}

_matches_cache: dict[str, list] = {}  # team_id -> matches
_scorecard_cache: dict[str, Optional[dict]] = {}  # match_id -> scorecard or None


async def _get(url: str, params: dict | None = None) -> httpx.Response:
    async with _SEMAPHORE:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            p = {"jsconfig": _JSCONFIG}
            if params:
                p.update(params)
            r = await client.get(url, params=p, headers=_HEADERS)
            if r.status_code == 429:
                await asyncio.sleep(1.0)
                r = await client.get(url, params=p, headers=_HEADERS)
            return r


async def get_team_matches(team_id: str) -> list[dict]:
    """Return all matches a team played in its season.

    Note: each team in Grassroots is bound to one season — so this returns
    that season's matches only. Fan out across all teams to get full history.
    """
    if team_id in _matches_cache:
        return _matches_cache[team_id]
    try:
        r = await _get(f"{BASE_URL}/scores/teams/{team_id}/matches")
        if r.status_code != 200:
            logger.debug(f"GR scores: /teams/{team_id}/matches → {r.status_code}")
            _matches_cache[team_id] = []
            return []
        data = r.json()
        matches = data.get("matches") or []
        _matches_cache[team_id] = matches
        return matches
    except Exception as e:
        logger.warning(f"GR scores: /teams/{team_id}/matches failed: {e}")
        return []


async def get_match_scorecard(match_id: str) -> Optional[dict]:
    """Return full scorecard for a match, or None if not in Grassroots (204).

    The 204 case isn't an error — it means this match is a post-migration
    PlayHQ-only game that Grassroots doesn't know about. The caller should
    skip it and let the PlayHQ sync path handle it.
    """
    if match_id in _scorecard_cache:
        return _scorecard_cache[match_id]
    try:
        r = await _get(f"{BASE_URL}/scores/matches/{match_id}", params={"responseModifier": "includeScorecard"})
        if r.status_code == 204:
            _scorecard_cache[match_id] = None
            return None
        if r.status_code != 200:
            logger.warning(f"GR scores: /matches/{match_id} → {r.status_code}: {r.text[:200]}")
            _scorecard_cache[match_id] = None
            return None
        data = r.json()
        _scorecard_cache[match_id] = data
        return data
    except Exception as e:
        logger.warning(f"GR scores: /matches/{match_id} failed: {e}")
        return None
