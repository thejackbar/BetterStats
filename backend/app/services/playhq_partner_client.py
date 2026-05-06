import asyncio
import httpx
import logging
import time
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = "https://api.playhq.com"
TENANT = "ca"
TIMEOUT = 15.0
CACHE_TTL = 300  # 5 minutes

_cache: dict[str, tuple[float, list]] = {}


def _headers() -> dict:
    return {
        "x-api-key": settings.playhq_api_key,
        "x-phq-tenant": TENANT,
    }


def _get_cached(key: str):
    if key in _cache:
        ts, val = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return val
    return None


def _set_cached(key: str, val):
    _cache[key] = (time.time(), val)
    return val


async def get_org_seasons(playhq_id: str) -> list:
    key = f"seasons:{playhq_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/v1/organisations/{playhq_id}/seasons",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return _set_cached(key, r.json().get("data", []))


async def get_season_grades(season_id: str) -> list:
    key = f"grades:{season_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/v1/seasons/{season_id}/grades",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return _set_cached(key, r.json().get("data", []))


async def get_grade_games(grade_id: str) -> list:
    key = f"games:{grade_id}"
    cached = _get_cached(key)
    if cached is not None:
        return cached
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/v1/grades/{grade_id}/games",
            headers=_headers(),
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return _set_cached(key, r.json().get("data", []))


def _outcome_to_result(outcome: str) -> Optional[str]:
    return {"WON": "WIN", "LOST": "LOSS", "DREW": "DRAW", "TIE": "DRAW"}.get(outcome)


def _parse_game(game: dict, grade_name: str, season_name: str, keyword: str) -> Optional[dict]:
    competitors = game.get("competitors", [])
    our_teams = [c for c in competitors if keyword and keyword in c.get("name", "").lower()]
    if not our_teams:
        return None

    our_team = our_teams[0]
    home = next((c for c in competitors if c.get("isHomeTeam")), competitors[0] if competitors else {})
    away = next((c for c in competitors if not c.get("isHomeTeam")), competitors[-1] if len(competitors) > 1 else {})
    winner = next((c.get("name") for c in competitors if c.get("outcome") == "WON"), None)
    schedule = game.get("schedule", {})
    venue = game.get("venue") or {}

    return {
        "id": game.get("id"),
        "status": game.get("status"),
        "played_at": schedule.get("date"),
        "time": schedule.get("time"),
        "home_team": home.get("name", ""),
        "away_team": away.get("name", ""),
        "home_score": home.get("scoreTotal"),
        "away_score": away.get("scoreTotal"),
        "result": _outcome_to_result(our_team.get("outcome", "")),
        "winning_team": winner,
        "grade": {"name": grade_name},
        "season": season_name,
        "round": (game.get("round") or {}).get("name"),
        "venue": venue.get("name"),
        "url": game.get("url"),
    }


async def get_org_games(playhq_id: str, org_name: str) -> list:
    """Fetch all recent games for an org across its most recent seasons."""
    if not settings.playhq_api_key or not playhq_id:
        return []

    try:
        seasons = await get_org_seasons(playhq_id)
    except Exception as e:
        logger.warning(f"PlayHQ: failed to get seasons for {playhq_id}: {e}")
        return []

    recent_seasons = seasons[:6]
    if not recent_seasons:
        return []
    logger.info(f"PlayHQ: fetching games across {len(recent_seasons)} seasons for org {playhq_id}: {[s.get('name') for s in recent_seasons]}")

    # Fetch grades for all recent seasons concurrently
    grade_results = await asyncio.gather(
        *[get_season_grades(s["id"]) for s in recent_seasons],
        return_exceptions=True,
    )

    grade_season_pairs: list[tuple[dict, str]] = []
    for i, grades in enumerate(grade_results):
        if isinstance(grades, list):
            season_name = recent_seasons[i].get("name", "")
            for g in grades:
                grade_season_pairs.append((g, season_name))

    if not grade_season_pairs:
        return []

    # Fetch games for all grades concurrently
    game_results = await asyncio.gather(
        *[get_grade_games(g["id"]) for g, _ in grade_season_pairs],
        return_exceptions=True,
    )

    keyword = org_name.split()[0].lower() if org_name else ""
    all_games = []

    for i, games in enumerate(game_results):
        if not isinstance(games, list):
            continue
        grade, season_name = grade_season_pairs[i]
        grade_name = grade.get("name", "")
        for game in games:
            parsed = _parse_game(game, grade_name, season_name, keyword)
            if parsed:
                all_games.append(parsed)

    return all_games
