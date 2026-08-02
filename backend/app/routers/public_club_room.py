"""Club Room Mode — public link (unauthenticated).

Lets a club run the TV loop straight off /room/{token} with no admin session
on that browser — the same magic-link posture as BetterSelect's self-service
availability and vote-collection links, just gated by a single shared PIN
(set once by a club admin or Super Admin) rather than a per-player one, since
nobody needs to be identified here — only "is this a legitimate viewer".

Three controls, same as every other link in this app: a rotatable link
token (identifies the club only), an optional 4-digit PIN (proves the
visitor was given it), and a signed HttpOnly cookie (~30 days) so re-opening
the same browser tab doesn't ask again. hash_pin/verify_pin are the same
bcrypt helpers services/club_lock.py uses for the password-protected "Draft"
club pages, but the cookie here is its own (`bs_clubroom`, `typ: "room"`) —
unlocking a Draft-mode page and unlocking a Club Room link are different
secrets the admin may set differently, so they don't share a cookie.

NOT behind require_module (no session): the token resolves the club and this
router checks `public_link_enabled` itself, same tell-nothing-on-a-bad-token
posture as the other public links.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config.settings import settings
from app.models.db import ClubRoomSettings, Organisation, get_db
from app.routers.club_room import build_play_payload
from app.services import club_lock, rate_limit

router = APIRouter(prefix="/public/club-room", tags=["public-club-room"])

COOKIE_NAME = "bs_clubroom"
SESSION_DAYS = 30
PIN_MAX_FAILURES = 5
PIN_LOCKOUT_SECONDS = 15 * 60
VERIFY_IP_LIMIT = 30
VERIFY_IP_WINDOW = 60


def _client_ip(request: Request) -> str:
    for header in ("cf-connecting-ip", "x-real-ip"):
        v = request.headers.get(header)
        if v:
            return v.strip()
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _issue_cookie(response: Response, org_id) -> None:
    exp = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)
    token = jwt.encode(
        {"org": str(org_id), "typ": "room", "exp": exp},
        settings.secret_key,
        algorithm=settings.algorithm,
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=SESSION_DAYS * 24 * 60 * 60,
        path="/",
    )


def _is_unlocked(request: Request, org_id) -> bool:
    raw = request.cookies.get(COOKIE_NAME)
    if not raw:
        return False
    try:
        payload = jwt.decode(raw, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return False
    return payload.get("typ") == "room" and payload.get("org") == str(org_id)


async def _club_for_token(db: AsyncSession, token: str) -> tuple[Organisation, ClubRoomSettings]:
    """Resolve the club + settings behind a Club Room link token, or 404 —
    same tell-nothing posture whether the token is unknown or just not
    published (public_link_enabled off), so a guess can't distinguish them."""
    if not token:
        raise HTTPException(status_code=404, detail="Unknown link")
    res = await db.execute(select(ClubRoomSettings).where(ClubRoomSettings.link_token == token))
    s = res.scalar_one_or_none()
    club = await db.get(Organisation, s.organisation_id) if s else None
    if s is None or club is None or not s.public_link_enabled:
        raise HTTPException(status_code=404, detail="This link isn't active")
    return club, s


@router.get("/{token}")
async def landing(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, s = await _club_for_token(db, token)
    return {
        "club_name": club.name,
        "club_short": club.short_name or (club.name or "")[:2].upper(),
        "logo_url": (f"/api/images/organisations/{club.id}/logo" if club.logo_data or club.logo_url else None),
        "require_pin": s.require_pin,
        "unlocked": (not s.require_pin) or _is_unlocked(request, club.id),
    }


class VerifyBody(BaseModel):
    pin: str = ""


@router.post("/{token}/verify")
async def verify(token: str, body: VerifyBody, request: Request, response: Response, db: AsyncSession = Depends(get_db)):
    club, s = await _club_for_token(db, token)
    if not s.require_pin:
        _issue_cookie(response, club.id)
        return {"ok": True}

    ip = _client_ip(request)
    key = f"clubroom-verify:{token}:{ip}"
    rate_limit.enforce(f"clubroom-verify-rate:{token}:{ip}", VERIFY_IP_LIMIT, VERIFY_IP_WINDOW)
    rate_limit.assert_not_locked(key, PIN_MAX_FAILURES, PIN_LOCKOUT_SECONDS, detail="Too many attempts. Try again later.")

    if not club_lock.verify_pin(body.pin, s.pin_hash):
        rate_limit.record_failure(key, PIN_LOCKOUT_SECONDS)
        raise HTTPException(status_code=401, detail="Wrong PIN")

    rate_limit.clear_failures(key)
    _issue_cookie(response, club.id)
    return {"ok": True}


@router.get("/{token}/play")
async def play(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    club, s = await _club_for_token(db, token)
    if s.require_pin and not _is_unlocked(request, club.id):
        raise HTTPException(status_code=401, detail="PIN required")
    return await build_play_payload(db, club)
