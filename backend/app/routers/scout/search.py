"""BetterScout — the one global search bar (clubs + players together). Read-
only, open to either role (see routers/scout/discovery.py's docstring for
the read/write role split). See services/scout_search.py for why this fans
out to the two existing search primitives rather than mirroring PlayHQ's own
search API (unreachable — probed live, see that module's docstring).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user
from app.services import scout_search

router = APIRouter(prefix="/scout", tags=["scout-search"])


@router.get("/search")
async def unified_search(
    q: str = "",
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    return await scout_search.unified_search(db, q)
