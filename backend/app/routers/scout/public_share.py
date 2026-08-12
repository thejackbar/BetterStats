"""BetterScout — the one unauthenticated route in this module: resolving a
per-card read-only share link. No Scout Org login, no PIN, no session
cookie — the token itself is the credential (see
services/scout_watchlist.get_shared_card for why that's a safe trade-off
here and not for anything else in this app). 404, never 403, on a
missing/revoked token — a dead link should reveal nothing."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutInvite, ScoutOrg
from app.services import scout_compare, scout_invites, scout_watchlist

router = APIRouter(prefix="/public/scout", tags=["scout-public-share"])


@router.get("/share/{token}")
async def get_shared_card(token: str, db: AsyncSession = Depends(get_db)):
    card = await scout_watchlist.get_shared_card(db, token)
    if card is None:
        raise HTTPException(status_code=404, detail="This share link isn't valid.")
    return card


@router.get("/compare/{token}")
async def get_shared_comparison(token: str, db: AsyncSession = Depends(get_db)):
    data = await scout_compare.get_shared_comparison(db, token)
    if data is None:
        raise HTTPException(status_code=404, detail="This share link isn't valid.")
    return data


# ─── invite accept — the second unauthenticated route in this module ───────

@router.get("/invite/{token}")
async def preview_invite(token: str, db: AsyncSession = Depends(get_db)):
    """Lets the accept-invite page show which org/email/role a link is for
    before asking someone to pick a username and password."""
    invite = (await db.execute(select(ScoutInvite).where(ScoutInvite.token == token))).scalar_one_or_none()
    if not invite or invite.accepted_at is not None:
        raise HTTPException(status_code=404, detail="This invite isn't valid.")
    org = await db.get(ScoutOrg, invite.scout_org_id)
    return {"email": invite.email, "role": invite.role, "scout_org_name": org.name if org else None}


class AcceptInviteRequest(BaseModel):
    username: str
    password: str
    display_name: str | None = None


@router.post("/invite/{token}/accept")
async def accept_invite(token: str, data: AcceptInviteRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await scout_invites.accept_invite(db, token, data.username, data.password, data.display_name)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
