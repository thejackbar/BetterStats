"""BetterScout — login/session routes. See services/scout_auth.py for why
this is its own scheme rather than reusing routers/auth.py."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.services import scout_auth, scout_billing, scout_milestones

router = APIRouter(prefix="/scout/auth", tags=["scout-auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


async def get_current_scout_user(
    request: Request, db: AsyncSession = Depends(get_db)
) -> tuple[ScoutUser, ScoutOrg]:
    resolved = scout_auth.read_session(request)
    if not resolved:
        raise HTTPException(status_code=401, detail="Not authenticated")
    org_id, user_id = resolved

    user = await db.get(ScoutUser, user_id)
    if not user or user.scout_org_id != org_id:
        raise HTTPException(status_code=401, detail="Not authenticated")

    org = await db.get(ScoutOrg, org_id)
    if not org or not org.is_active:
        raise HTTPException(status_code=401, detail="Not authenticated")

    return user, org


async def require_scout_owner(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
) -> tuple[ScoutUser, ScoutOrg]:
    """Org-wide actions (settings, billing, inviting/removing teammates,
    share-link bulk management) need the 'owner' role — a 'viewer' can read
    everything but shouldn't be able to change what the org is or who's in
    it. See services/scout_watchlist.py / scout_discovery.py's own write
    endpoints for the per-record ownership check every route already has;
    this is the ADDITIONAL org-wide layer on top of it."""
    user, org = current
    if user.role != "owner":
        raise HTTPException(status_code=403, detail="Only an org owner can do this.")
    return current


def _build_me(user: ScoutUser, org: ScoutOrg, usage: dict, milestones_unseen_count: int = 0) -> dict:
    return {
        "id": str(user.id),
        "username": user.username,
        "display_name": user.display_name,
        "role": user.role,
        "scout_org_id": str(org.id),
        "scout_org_name": org.name,
        "scout_org_slug": org.slug,
        "theme": {
            "primary_color": org.primary_color,
            "accent_color": org.accent_color,
            "theme_mode": org.theme_mode,
        },
        "usage": usage,
        # Reached-but-not-yet-marked-seen milestones — see
        # services/scout_milestones.py's ScoutMilestoneSeen docstring.
        "milestones_unseen_count": milestones_unseen_count,
    }


@router.post("/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    username = (data.username or "").strip().lower()
    result = await db.execute(select(ScoutUser).where(ScoutUser.username == username))
    user = result.scalar_one_or_none()

    # Generic error either way — don't leak which field was wrong.
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = datetime.now(timezone.utc)

    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(status_code=429, detail="Account temporarily locked. Try again later.")

    if not scout_auth.verify_password(data.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= scout_auth.MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=scout_auth.LOCKOUT_MINUTES)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    org = await db.get(ScoutOrg, user.scout_org_id)
    if not org or not org.is_active:
        raise HTTPException(status_code=403, detail="Scout org is not active")

    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    scout_auth.issue_session_cookie(response, org.id, user.id)
    usage = await scout_billing.usage_for(db, org)
    unseen = await scout_milestones.unseen_reached_count(db, org.id)
    return _build_me(user, org, usage, unseen)


@router.post("/logout")
async def logout(response: Response):
    scout_auth.clear_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/me")
async def me(
    current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user),
    db: AsyncSession = Depends(get_db),
):
    user, org = current
    usage = await scout_billing.usage_for(db, org)
    unseen = await scout_milestones.unseen_reached_count(db, org.id)
    return _build_me(user, org, usage, unseen)
