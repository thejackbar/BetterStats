"""BetterScout — Player Name Search & Hot Form Feed. Both read-only, both
open to either role (same "reads are open to either role" rule
routers/scout/discovery.py's docstring sets) — neither mutates any org's own
tracked-player state. See services/scout_feed.py for the platform-wide,
cached-club scope both of these operate under.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.routers.scout.auth import get_current_scout_user
from app.services import scout_feed

router = APIRouter(prefix="/scout/feed", tags=["scout-feed"])


@router.get("/search")
async def search_players(
    q: str = "",
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_feed.search_players(db, str(org.id), q)


@router.get("/hot-form")
async def hot_form(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    _, org = current
    return await scout_feed.hot_form_feed(db, str(org.id))
