from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
import bcrypt as _bcrypt
from jose import JWTError, jwt
from datetime import datetime, timedelta, timezone
import uuid

from app.models.db import User, ClubMembership, Organisation, get_db
from app.config.settings import settings

router = APIRouter(prefix="/auth", tags=["auth"])


def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode())


def _hash_password(plain: str) -> str:
    return _bcrypt.hashpw(plain.encode(), _bcrypt.gensalt()).decode()

COOKIE_NAME = "bs_session"
MAX_FAILED_ATTEMPTS = 5
LOCKOUT_MINUTES = 15


def _create_token(user_id: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    return jwt.encode({"sub": user_id, "exp": expire}, settings.secret_key, algorithm=settings.algorithm)


def _set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
    )


async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        user_id: str = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    user = await db.get(User, uuid.UUID(user_id))
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return user


async def require_super_admin(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> User:
    result = await db.execute(
        select(ClubMembership).where(
            ClubMembership.user_id == current_user.id,
            ClubMembership.role == "super_admin",
        )
    )
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Super admin access required")
    return current_user


def _effective_club_id(membership: ClubMembership | None, user: User) -> uuid.UUID | None:
    """The club a request is scoped to.

    Super admins are Better staff who manage every club, so they can "act as"
    any club via ``User.active_club_id`` (set through ``POST /auth/switch-club``).
    Everyone else is pinned to the single club on their membership — the override
    is ignored for non-super roles, so it can never widen a club admin's reach.
    """
    if membership is None:
        return None
    if membership.role == "super_admin" and getattr(user, "active_club_id", None):
        return user.active_club_id
    return membership.club_id


async def get_current_club(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Organisation:
    result = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No club membership found")
    eff_id = _effective_club_id(membership, current_user)
    club = await db.get(Organisation, eff_id) if eff_id else None
    # A dangling active_club_id (e.g. the acted-as club was deleted) falls back
    # to the staff member's home membership club rather than 403-ing them out.
    if club is None and eff_id != membership.club_id:
        club = await db.get(Organisation, membership.club_id)
    if not club:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Club not found")
    return club


class LoginRequest(BaseModel):
    username: str
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    username: str | None
    display_name: str | None
    role: str | None = None

    class Config:
        from_attributes = True


@router.post("/login")
async def login(data: LoginRequest, response: Response, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(User).where(User.username == data.username.lower()))
    user = result.scalar_one_or_none()

    # Generic error — do not leak which field was wrong
    if not user or not user.password_hash:
        raise HTTPException(status_code=401, detail="Invalid username or password")

    now = datetime.now(timezone.utc)

    # Check lockout
    if user.locked_until and user.locked_until.replace(tzinfo=timezone.utc) > now:
        raise HTTPException(status_code=429, detail="Account temporarily locked. Try again later.")

    if not _verify_password(data.password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= MAX_FAILED_ATTEMPTS:
            user.locked_until = now + timedelta(minutes=LOCKOUT_MINUTES)
        await db.commit()
        raise HTTPException(status_code=401, detail="Invalid username or password")

    # Check user has an active club membership (super_admin bypasses the is_active check)
    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == user.id)
    )
    membership = membership_res.scalar_one_or_none()
    if not membership:
        raise HTTPException(status_code=403, detail="No club membership found")

    club = await db.get(Organisation, membership.club_id)
    if membership.role != "super_admin":
        if not club or not club.is_active:
            raise HTTPException(status_code=403, detail="Club is not active")

    # Success — reset counters, update last login
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = now
    await db.commit()

    token = _create_token(str(user.id))
    _set_session_cookie(response, token)

    return await _build_me(user, db)


@router.post("/logout")
async def logout(response: Response):
    response.delete_cookie(key=COOKIE_NAME, path="/")
    return {"status": "logged_out"}


async def _build_me(current_user: User, db: AsyncSession) -> dict:
    """The shared identity payload returned by /login, /me and /switch-club.

    For a super admin this resolves to whichever club they're currently acting
    as (``active_club_id``), and also carries the home-club + acting flags the
    frontend club switcher needs.
    """
    from app.auth.capabilities import effective_capabilities
    from app.auth.modules import entitlement_summary

    membership_res = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = membership_res.scalar_one_or_none()
    role = membership.role if membership else None
    caps = effective_capabilities(role, membership.capabilities if membership else None) if role else []

    home_club = await db.get(Organisation, membership.club_id) if membership else None
    eff_id = _effective_club_id(membership, current_user)
    club = await db.get(Organisation, eff_id) if eff_id else None
    # active_club_id may dangle (acted-as club deleted) — fall back to home.
    if club is None and membership is not None:
        club = home_club
        eff_id = membership.club_id

    is_super = role == "super_admin"
    acting = bool(is_super and home_club and club and club.id != home_club.id)

    return {
        "id": str(current_user.id),
        "username": current_user.username,
        "display_name": current_user.display_name,
        "role": role,
        "club_id": str(eff_id) if eff_id else None,
        "club_slug": club.slug if club else None,
        "club_name": club.name if club else None,
        "capabilities": caps,
        "entitlements": entitlement_summary(club, role),
        # Super-admin club-switch context. can_switch_clubs gates the UI switcher;
        # acting_as_club is true only while scoped to a club other than home.
        "can_switch_clubs": is_super,
        "home_club_id": str(membership.club_id) if membership else None,
        "home_club_name": home_club.name if home_club else None,
        "acting_as_club": acting,
    }


@router.get("/me")
async def me(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    return await _build_me(current_user, db)


class SwitchClubRequest(BaseModel):
    # None / omitted resets the super admin back to their home club.
    club_id: str | None = None


@router.post("/switch-club")
async def switch_club(
    data: SwitchClubRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Super-admin-only: re-scope the whole admin app to another club.

    Persists the choice on the user row so every subsequent club-scoped request
    (and a page reload) resolves to the acted-as club until they switch again.
    """
    result = await db.execute(
        select(ClubMembership).where(ClubMembership.user_id == current_user.id)
    )
    membership = result.scalar_one_or_none()
    if not membership or membership.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admins can switch clubs")

    if not data.club_id:
        current_user.active_club_id = None
    else:
        try:
            target_id = uuid.UUID(data.club_id)
        except ValueError:
            raise HTTPException(status_code=422, detail="Invalid club id")
        target = await db.get(Organisation, target_id)
        if not target:
            raise HTTPException(status_code=404, detail="Club not found")
        # Acting as the home club is just the cleared state — keep it NULL so
        # acting_as_club reads false.
        current_user.active_club_id = None if target_id == membership.club_id else target_id

    await db.commit()
    await db.refresh(current_user)
    return await _build_me(current_user, db)
