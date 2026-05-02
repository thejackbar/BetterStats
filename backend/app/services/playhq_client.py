import httpx
import asyncio
import logging
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

BASE_URL = settings.playhq_base_url
DEFAULT_TIMEOUT = 30.0


async def _paginate(client: httpx.AsyncClient, url: str, params: dict = None) -> list:
    results = []
    cursor = None
    params = params or {}

    while True:
        if cursor:
            params["cursor"] = cursor
        r = await client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        r.raise_for_status()
        data = r.json()
        items = data.get("data", [])
        results.extend(items)
        meta = data.get("metadata", {})
        if not meta.get("hasMore"):
            break
        cursor = meta.get("cursor")

    return results


async def get_organisation(org_id: str) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/v1/organisations/{org_id}", timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            return data.get("data")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise


async def get_seasons(org_id: str) -> list:
    async with httpx.AsyncClient() as client:
        return await _paginate(client, f"{BASE_URL}/v1/organisations/{org_id}/seasons")


async def get_grades(season_id: str) -> list:
    async with httpx.AsyncClient() as client:
        return await _paginate(client, f"{BASE_URL}/v1/seasons/{season_id}/grades")


async def get_fixtures(grade_id: str) -> list:
    async with httpx.AsyncClient() as client:
        return await _paginate(client, f"{BASE_URL}/v1/grades/{grade_id}/fixture")


async def get_game_summary(game_id: str) -> Optional[dict]:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(f"{BASE_URL}/v1/games/{game_id}/summary", timeout=DEFAULT_TIMEOUT)
            r.raise_for_status()
            data = r.json()
            return data.get("data")
        except httpx.HTTPStatusError as e:
            logger.warning(f"Failed to fetch game {game_id}: {e.response.status_code}")
            return None
        except Exception as e:
            logger.error(f"Error fetching game {game_id}: {e}")
            return None


async def get_games_batch(game_ids: list[str], concurrency: int = 5) -> list[dict]:
    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_one(game_id: str) -> Optional[dict]:
        async with semaphore:
            return await get_game_summary(game_id)

    results = await asyncio.gather(*[fetch_one(gid) for gid in game_ids], return_exceptions=False)
    return [r for r in results if r is not None]
