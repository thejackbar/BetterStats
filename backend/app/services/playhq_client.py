import httpx
import logging
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.playhq_base_url
DEFAULT_TIMEOUT = 30.0
_JSCONFIG = "eccn:true"


def _base_params(extra: dict = None) -> dict:
    params = {"jsconfig": _JSCONFIG}
    if extra:
        params.update(extra)
    return params


async def search_organisations(query: str) -> list:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/orgsproducts/organisation/search",
            params=_base_params({"searchString": query}),
            timeout=DEFAULT_TIMEOUT,
        )
        r.raise_for_status()
        data = r.json()
        return data.get("data", data.get("organisations", data if isinstance(data, list) else []))


async def get_organisation(org_id: str) -> Optional[dict]:
    """Validate an org exists by probing the batting-statistics endpoint."""
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/participants/organisations/{org_id}/batting-statistics",
                params=_base_params(),
                timeout=DEFAULT_TIMEOUT,
            )
            if r.status_code == 404:
                return None
            r.raise_for_status()
            return {"id": org_id, "name": "", "shortName": ""}
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise


async def get_seasons(org_id: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/fixturesladders/organisations/{org_id}/seasons",
                params=_base_params(),
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("data", data.get("seasons", data if isinstance(data, list) else []))
        except Exception as e:
            logger.warning(f"get_seasons failed for {org_id}: {e}")
            return []


async def get_teams(org_id: str, season_id: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/fixturesladders/organisations/{org_id}/teams",
                params=_base_params({"seasonId": season_id}),
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            return data.get("data", data.get("teams", data if isinstance(data, list) else []))
        except Exception as e:
            logger.warning(f"get_teams failed for org={org_id} season={season_id}: {e}")
            return []


async def _paginate_stats(url: str, season_id: str, extra_params: dict = None) -> list:
    results = []
    offset = 1
    limit = 100
    async with httpx.AsyncClient() as client:
        while True:
            params = _base_params({"seasonId": season_id, "offset": offset, "limit": limit})
            if extra_params:
                params.update(extra_params)
            r = await client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            items = data.get("data", data.get("participants", data if isinstance(data, list) else []))
            if not items:
                break
            results.extend(items)
            if len(items) < limit:
                break
            offset += limit
    return results


async def get_batting_stats(org_id: str, season_id: str) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/batting-statistics",
        season_id,
        {"sort": "BattingAggregate:desc"},
    )


async def get_bowling_stats(org_id: str, season_id: str) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/bowling-statistics",
        season_id,
        {"sort": "BowlingWickets:desc"},
    )


async def get_fielding_stats(org_id: str, season_id: str) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/fielding-statistics",
        season_id,
    )


# Stubs retained for backward compatibility
async def get_grades(season_id: str) -> list:
    return []


async def get_fixtures(grade_id: str) -> list:
    return []


async def get_game_summary(game_id: str) -> Optional[dict]:
    return None


async def get_games_batch(game_ids: list[str], concurrency: int = 5) -> list[dict]:
    return []
