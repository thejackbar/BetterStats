import asyncio
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


# The CA proxy rejects search strings over 20 characters with a 400
# ('MaximumLength'), so a pasted full club name ("Murdoch University Melville
# Cricket Club") returned nothing. Clip to whole words under the limit — the
# search matches on the leading words anyway.
_MAX_SEARCH_LEN = 20


async def search_organisations(query: str) -> list:
    query = (query or "").strip()
    if len(query) > _MAX_SEARCH_LEN:
        clipped = query[:_MAX_SEARCH_LEN]
        if query[_MAX_SEARCH_LEN] != " " and " " in clipped:
            clipped = clipped.rsplit(" ", 1)[0]
        query = clipped.strip()
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{BASE_URL}/orgsproducts/organisation/search",
            params=_base_params({"searchString": query}),
            timeout=DEFAULT_TIMEOUT,
        )
        if r.status_code >= 400:
            # A bad query shouldn't 500 the caller's endpoint — empty is honest.
            logger.warning(f"search_organisations: {r.status_code} for {query!r}: {r.text[:120]}")
            return []
        data = r.json()
        orgs = data.get("data", data.get("organisations", data if isinstance(data, list) else []))
        # Expose the Grassroots organisation GUID as `id` — that is the key
        # every sync endpoint resolves against. `playHQId` is a separate
        # namespace; the fixturesladders/scores APIs don't recognise it, so
        # binding a club to it yields an empty (0-season) sync.
        for org in orgs:
            if not org.get("id"):
                org["id"] = org.get("organisationGuid") or org.get("playHQId")
        return orgs


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
    all_seasons: list = []
    offset = 1
    limit = 100
    async with httpx.AsyncClient() as client:
        while True:
            try:
                r = await client.get(
                    f"{BASE_URL}/fixturesladders/organisations/{org_id}/seasons",
                    params=_base_params({"offset": offset, "limit": limit}),
                    timeout=DEFAULT_TIMEOUT,
                )
                r.raise_for_status()
                data = r.json()
                batch = data.get("data", data.get("seasons", data if isinstance(data, list) else []))
                if not batch:
                    break
                all_seasons.extend(batch)
                if len(batch) < limit:
                    break
                offset += limit
            except Exception as e:
                logger.warning(f"get_seasons failed for {org_id} at offset={offset}: {e}")
                break
    logger.info(f"Grassroots API: got {len(all_seasons)} seasons for org {org_id}")
    return all_seasons


async def get_grades(org_id: str, season_id: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            r = await client.get(
                f"{BASE_URL}/fixturesladders/organisations/{org_id}/grades",
                params=_base_params({"seasonId": season_id}),
                timeout=DEFAULT_TIMEOUT,
            )
            r.raise_for_status()
            data = r.json()
            grades = data.get("data", data.get("grades", data if isinstance(data, list) else []))
            logger.debug(f"get_grades org={org_id} season={season_id}: {len(grades)} grades")
            return grades
        except Exception as e:
            logger.debug(f"get_grades failed for org={org_id} season={season_id}: {e}")
            return []


async def get_teams(org_id: str, season_id: str) -> list:
    async with httpx.AsyncClient() as client:
        try:
            r = await _get_with_retry(
                client,
                f"{BASE_URL}/fixturesladders/organisations/{org_id}/teams",
                _base_params({"seasonId": season_id}),
            )
            r.raise_for_status()
            data = r.json()
            return data.get("data", data.get("teams", data if isinstance(data, list) else []))
        except Exception as e:
            logger.warning(f"get_teams failed for org={org_id} season={season_id}: {e}")
            return []


async def _get_with_retry(client: "httpx.AsyncClient", url: str, params: dict, retries: int = 3):
    """GET with backoff on transient connection failures (DNS blips, refused
    connections, etc). A hard refresh wipes game-level data before this runs,
    so a single dropped connection shouldn't be allowed to abort the whole
    resync and leave the club with no games — retry a few times before giving
    up and letting the caller treat it as "no data this page"."""
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            return await client.get(url, params=params, timeout=DEFAULT_TIMEOUT)
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout) as e:
            last_exc = e
            if attempt < retries - 1:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_exc


async def _paginate_stats(url: str, season_id: str, extra_params: dict = None, grade_id: Optional[str] = None) -> list:
    results = []
    offset = 1
    limit = 100
    try:
        async with httpx.AsyncClient() as client:
            while True:
                params = _base_params({"seasonId": season_id, "offset": offset, "limit": limit})
                if grade_id:
                    params["gradeId"] = grade_id
                if extra_params:
                    params.update(extra_params)
                r = await _get_with_retry(client, url, params)
                r.raise_for_status()
                # A season with no stats returns 204 / an empty body — that's a
                # valid "nothing here", not an error. Calling .json() on it raises
                # "Expecting value: line 1 column 1 (char 0)".
                if r.status_code == 204 or not r.content:
                    break
                try:
                    data = r.json()
                except ValueError:
                    logger.warning(f"_paginate_stats: non-JSON body from {url} (status {r.status_code})")
                    break
                items = data.get("data", data.get("participants", data if isinstance(data, list) else []))
                if not items:
                    break
                results.extend(items)
                if len(items) < limit:
                    break
                offset += limit
    except Exception as e:
        # Don't let a mid-pagination failure (upstream blip after retries
        # exhausted) crash the whole sync — surface what was gathered so far
        # and let the caller's usual "no data" handling take it from here.
        logger.warning(f"_paginate_stats: {url} failed at offset={offset}: {e}")
    return results


async def get_batting_stats(org_id: str, season_id: str, grade_id: Optional[str] = None) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/batting-statistics",
        season_id,
        {"sort": "BattingAggregate:desc"},
        grade_id=grade_id,
    )


async def get_bowling_stats(org_id: str, season_id: str, grade_id: Optional[str] = None) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/bowling-statistics",
        season_id,
        {"sort": "BowlingWickets:desc"},
        grade_id=grade_id,
    )


async def get_fielding_stats(org_id: str, season_id: str, grade_id: Optional[str] = None) -> list:
    return await _paginate_stats(
        f"{BASE_URL}/participants/organisations/{org_id}/fielding-statistics",
        season_id,
        grade_id=grade_id,
    )


async def lookup_playhq_id(org_guid: str, org_name: str) -> Optional[str]:
    """Search the grassroots API to find the PlayHQ native ID for an org GUID."""
    first_word = (org_name or "").split()[0] if org_name else ""
    if not first_word:
        return None
    try:
        orgs = await search_organisations(first_word)
        for o in orgs:
            guid = str(o.get("organisationGuid") or o.get("id") or "")
            if guid.lower() == org_guid.lower():
                return o.get("playHQId")
    except Exception as e:
        logger.warning(f"lookup_playhq_id failed for {org_guid}: {e}")
    return None


async def get_fixtures(grade_id: str) -> list:
    return []


async def get_game_summary(game_id: str) -> Optional[dict]:
    return None


async def get_games_batch(game_ids: list[str], concurrency: int = 5) -> list[dict]:
    return []
