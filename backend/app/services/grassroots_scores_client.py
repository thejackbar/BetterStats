"""Grassroots /scores/* client — Cricket Australia's pre-PlayHQ match data.

Key unauthenticated endpoints on grassrootsapiproxy.cricket.com.au:
  /scores/grades/{grade_id}/matches          — all matches in a grade (primary discovery)
  /scores/teams/{team_id}/matches            — all matches a team played (fallback)
  /scores/matches/{id}?responseModifier=includeScorecard — full scorecard

Data reaches back to at least 1975. Post-migration PlayHQ games return 204 —
that signals "not mine" cleanly, no de-dup needed.

participantId values in the response correspond directly to our players.id
column (both are Grassroots GUIDs), so no extra mapping table is required.
"""
import asyncio
import logging
import time
from datetime import date
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

_grade_matches_cache: dict[str, list] = {}  # grade_id -> matches
_matches_cache: dict[str, list] = {}  # team_id -> matches
_scorecard_cache: dict[str, Optional[dict]] = {}  # match_id -> scorecard or None
_ladder_cache: dict[str, tuple] = {}  # grade_id -> (fetched_at, data | None)
_LADDER_TTL = 3600  # ladders move ~weekly; an hour keeps the proxy happy


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


async def get_grade_matches(grade_id: str) -> list[dict]:
    """Return all matches in a grade.

    Uses /scores/grades/{grade_id}/matches — unauthenticated, works for all
    seasons including pre-2000 data. Preferred over team-based discovery
    because it doesn't require fixturesladders (which has no records for
    old seasons).
    """
    if grade_id in _grade_matches_cache:
        return _grade_matches_cache[grade_id]
    try:
        r = await _get(f"{BASE_URL}/scores/grades/{grade_id}/matches")
        if r.status_code != 200:
            logger.debug(f"GR scores: /grades/{grade_id}/matches → {r.status_code}")
            _grade_matches_cache[grade_id] = []
            return []
        data = r.json()
        matches = data.get("matches") or []
        _grade_matches_cache[grade_id] = matches
        return matches
    except Exception as e:
        logger.warning(f"GR scores: /grades/{grade_id}/matches failed: {e}")
        return []


async def get_grade_ladder(grade_id: str) -> Optional[dict]:
    """Return the live ladder/standings for a grade.

    Uses /fixturesladders/grades/{grade_id}/ladders — unauthenticated, 200 OK
    for current grades (grade_id is the same UUID as grades.id in our DB).
    Returns the raw JSON dict, or None on any non-200 / failure. Cached for an
    hour. The response *shape* is normalised by the caller, defensively.
    """
    now = time.time()
    hit = _ladder_cache.get(grade_id)
    if hit and now - hit[0] < _LADDER_TTL:
        return hit[1]
    try:
        r = await _get(f"{BASE_URL}/fixturesladders/grades/{grade_id}/ladders")
        if r.status_code != 200:
            logger.debug(f"GR ladders: /grades/{grade_id}/ladders → {r.status_code}")
            _ladder_cache[grade_id] = (now, None)
            return None
        data = r.json()
        _ladder_cache[grade_id] = (now, data)
        return data
    except Exception as e:
        logger.warning(f"GR ladders: /grades/{grade_id}/ladders failed: {e}")
        return None


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


_balls_cache: dict[str, Optional[dict]] = {}  # match_id -> ball-by-ball or None


async def get_match_balls(match_id: str) -> Optional[dict]:
    """Return ball-by-ball data for a match, or None if not available.

    Uses /scores/matches/{id}/balls — unauthenticated, returns
    ``{teams:[{id, owningOrganisation:{id,name}, ...}], innings:[{battingTeamId,
    balls:[{overNumber, runsBat, wides, noBalls, legByes, byes, penaltyRuns,
    dismissedParticipantId, ...}]}]}`` for live-scored matches (the scorecard
    flags these ``isBallByBall: true``). Most historical games are scorecard-only
    and 403/empty here — we treat any non-200 or empty ``innings`` as "no ball
    data" so callers can simply skip them.
    """
    if match_id in _balls_cache:
        return _balls_cache[match_id]
    try:
        r = await _get(f"{BASE_URL}/scores/matches/{match_id}/balls")
        if r.status_code != 200:
            _balls_cache[match_id] = None
            return None
        data = r.json()
        if not data.get("innings"):
            _balls_cache[match_id] = None
            return None
        _balls_cache[match_id] = data
        return data
    except Exception as e:
        logger.warning(f"GR balls: /matches/{match_id}/balls failed: {e}")
        _balls_cache[match_id] = None
        return None


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


# ── Upcoming fixtures ────────────────────────────────────────────────────────
# CA's restricted /fixturesladders/.../fixtures endpoints are 403 with the public
# key, but /scores/grades/{id}/matches returns EVERY match in a grade keyed by a
# status enum (verified live against an in-season winter comp):
#   0=UPCOMING  2=LIVE  3=COMPLETED  4=ABANDONED  5=NO RESULT
# Upcoming fixtures are simply the rows whose status is pre-completion and whose
# scheduled date is today-or-later. grade_id MUST be the raw CA grade GUID
# (grades.grassroots_id, COALESCE'd with id for legacy rows).
_FIXTURE_STATUS_UPCOMING = 0
_FIXTURE_STATUS_LIVE = 2
_FIXTURE_STATUS_COMPLETED = 3


async def get_grade_results(grade_id: str, *, since: Optional[str] = None) -> list[dict]:
    """Completed matches for one grade, normalised (the results mirror of
    ``get_grade_fixtures``).

    Reuses ``get_grade_matches`` (same in-process cache). Returns
    ``{id, home_team, away_team, played_at, round, venue, grade_id}`` for
    matches in the terminal COMPLETED state (statusId 3). Scores/result are NOT
    in the match list — the caller fetches ``get_match_scorecard(id)`` for those,
    exactly like the single-scorecard import. ``since`` (YYYY-MM-DD) drops
    anything older, keeping the scorecard fan-out bounded to recent rounds.
    """
    matches = await get_grade_matches(grade_id)
    out: list[dict] = []
    for m in matches:
        try:
            sid = int(m.get("statusId"))
        except (TypeError, ValueError):
            continue
        if sid != _FIXTURE_STATUS_COMPLETED:
            continue
        sched = (m.get("matchSchedule") or [{}])
        dt = (sched[0].get("startDateTime") if sched else "") or ""
        day = dt[:10]
        if not day:
            continue
        if since and day < since:
            continue
        teams = m.get("teams") or []
        home = next((t.get("displayName") for t in teams if t.get("isHome")), None)
        away = next((t.get("displayName") for t in teams if not t.get("isHome")), None)
        out.append({
            "id": m.get("id"),
            "home_team": home,
            "away_team": away,
            "played_at": day,
            "round": (m.get("round") or {}).get("name"),
            "venue": (m.get("venue") or {}).get("name"),
            "grade_id": grade_id,
        })
    return out


async def get_grade_fixtures(grade_id: str, *, include_live: bool = True) -> list[dict]:
    """Upcoming (and optionally live) fixtures for one grade, normalised.

    Reuses ``get_grade_matches`` (same in-process cache). Returns a list of
    ``{id, home_team, away_team, played_at, time, status, round, venue, grade_id}``
    dicts for matches that haven't reached a terminal state and are scheduled
    today-or-later.
    """
    matches = await get_grade_matches(grade_id)
    today = date.today().isoformat()
    keep = {_FIXTURE_STATUS_UPCOMING}
    if include_live:
        keep.add(_FIXTURE_STATUS_LIVE)
    out: list[dict] = []
    for m in matches:
        try:
            sid = int(m.get("statusId"))
        except (TypeError, ValueError):
            continue
        if sid not in keep:
            continue
        sched = (m.get("matchSchedule") or [{}])
        dt = (sched[0].get("startDateTime") if sched else "") or ""
        day = dt[:10]
        if not day or day < today:
            continue
        teams = m.get("teams") or []
        home = next((t.get("displayName") for t in teams if t.get("isHome")), None)
        away = next((t.get("displayName") for t in teams if not t.get("isHome")), None)
        out.append({
            "id": m.get("id"),
            "home_team": home,
            "away_team": away,
            "played_at": day,
            "time": dt[11:16] if len(dt) >= 16 else None,
            "status": "LIVE" if sid == _FIXTURE_STATUS_LIVE else "UPCOMING",
            "round": (m.get("round") or {}).get("name"),
            "venue": (m.get("venue") or {}).get("name"),
            "grade_id": grade_id,
        })
    return out


async def get_grades_fixtures(
    grade_ids: list[str],
    match_keys: Optional[list[str]] = None,
    *,
    include_live: bool = True,
) -> list[dict]:
    """Aggregate ``get_grade_fixtures`` across grades, de-duplicated and sorted.

    ``match_keys`` (lowercased club name keys, e.g. from ``club_match_keys``)
    optionally restricts results to fixtures involving that club (substring match
    on either side). Grades are fetched concurrently; the underlying per-grade
    cache makes repeat calls cheap.
    """
    results = await asyncio.gather(
        *[get_grade_fixtures(g, include_live=include_live) for g in grade_ids],
        return_exceptions=True,
    )
    out: list[dict] = []
    seen: set = set()
    for r in results:
        if not isinstance(r, list):
            if isinstance(r, Exception):
                logger.warning(f"GR fixtures: grade fetch failed: {r}")
            continue
        for fx in r:
            fid = fx.get("id")
            if not fid or fid in seen:
                continue
            if match_keys:
                hl = (fx.get("home_team") or "").lower()
                al = (fx.get("away_team") or "").lower()
                if not any(k in hl or k in al for k in match_keys):
                    continue
            seen.add(fid)
            out.append(fx)
    out.sort(key=lambda x: (x["played_at"], x.get("time") or ""))
    return out
