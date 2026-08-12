"""BetterScout — login/session routes. See services/scout_auth.py for why
this is its own scheme rather than reusing routers/auth.py."""
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.db import get_db
from app.models.scout import ScoutOrg, ScoutUser
from app.services import scout_auth

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


def _build_me(user: ScoutUser, org: ScoutOrg) -> dict:
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
    return _build_me(user, org)


@router.post("/logout")
async def logout(response: Response):
    scout_auth.clear_session_cookie(response)
    return {"status": "logged_out"}


@router.get("/me")
async def me(current: tuple[ScoutUser, ScoutOrg] = Depends(get_current_scout_user)):
    user, org = current
    return _build_me(user, org)
