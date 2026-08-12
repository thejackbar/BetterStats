"""BetterScout — the one unauthenticated route in this module: resolving a
per-card read-only share link. No Scout Org login, no PIN, no session
cookie — the token itself is the credential (see
services/scout_watchlist.get_shared_card for why that's a safe trade-off
here and not for anything else in this app). 404, never 403, on a
missing/revoked token — a dead link should reveal nothing."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.services import scout_watchlist

router = APIRouter(prefix="/public/scout", tags=["scout-public-share"])


@router.get("/share/{token}")
async def get_shared_card(token: str, db: AsyncSession = Depends(get_db)):
    card = await scout_watchlist.get_shared_card(db, token)
    if card is None:
        raise HTTPException(status_code=404, detail="This share link isn't valid.")
    return card
