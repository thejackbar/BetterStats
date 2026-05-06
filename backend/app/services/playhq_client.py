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
        orgs = data.get("data", data.get("organisations", data if isinstance(data, list) else []))
        # Normalise: expose playHQId as id so the frontend can use org.id consistently
        for org in orgs:
            if "id" not in org and "playHQId" in org:
                org["id"] = org["playHQId"]
        return orgs
